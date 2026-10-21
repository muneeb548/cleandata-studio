"""AI assistant: the model is replaced by a fake, so these tests never use the network.

What matters here is the safety layer: whatever the model answers, only valid
operations on real columns come back, nothing is changed without preview/apply,
cloud use needs consent, and the request limit holds.
"""

import dataclasses
import json
import urllib.error

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import responses as R  # noqa: E402
from app.services import ai, ai_client  # noqa: E402

client = TestClient(app)

CSV = (
    "name,email,city,phone\n"
    "Ali Khan, ALI@GMAIL.COM ,Lhr,0300 1234567\n"
    "Sara,sara@gmail.com,lahore,+92 321 7654321\n"
    "Sara,sara@gmail.com,lahore,+92 321 7654321\n"
    "John,john@yahoo.com,LAHORE,\n"
    "Mia,mia@gmial.com,Karachi,\n"
)


class FakeModel:
    """Returns a fixed answer and remembers what it was sent."""

    def __init__(self, answer: dict):
        self.answer = answer
        self.calls: list[dict] = []
        self.provider, self.model = "fake", "fake"

    def complete_json(self, system, prompt, schema, max_tokens=2000):
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        return self.answer


@pytest.fixture
def use_ai(monkeypatch):
    def setup(answer: dict, provider: str = "ollama", **overrides) -> FakeModel:
        fake = FakeModel(answer)
        new = dataclasses.replace(settings, ai_provider=provider, anthropic_api_key="test-key", **overrides)
        monkeypatch.setattr(ai, "settings", new)
        monkeypatch.setattr(ai_client, "settings", new)
        monkeypatch.setattr(ai_client, "get_client", lambda: fake)
        return fake
    return setup


def upload(body: str = CSV) -> dict:
    r = client.post("/api/upload", params={"filename": "clients.csv"}, content=body.encode(),
                    headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 201, r.text
    return {"X-Session-Id": r.json()["session_id"]}


def step(operation: str, **settings_) -> dict:
    return {"operation": operation, "settings": json.dumps(settings_), "reason": "asked"}


# ----------------------------------------------------------------- status

def test_status_when_off(monkeypatch):
    # Independent of backend/.env on the developer's computer.
    off = dataclasses.replace(settings, ai_provider="off")
    monkeypatch.setattr(ai, "settings", off)
    monkeypatch.setattr(ai_client, "settings", off)
    data = R.AiStatus.model_validate(client.get("/api/ai/status").json())
    assert data.enabled is False and data.provider == "off" and data.ready is False


def test_status_reports_ollama_not_running(monkeypatch):
    new = dataclasses.replace(settings, ai_provider="ollama", ollama_url="http://127.0.0.1:9")
    monkeypatch.setattr(ai, "settings", new)
    monkeypatch.setattr(ai_client, "settings", new)
    data = client.get("/api/ai/status").json()
    assert data["enabled"] is True and data["ready"] is False and data["local"] is True
    assert "Ollama" in data["problem"] and data["needs_consent"] is False


def test_status_cloud_needs_consent(monkeypatch):
    new = dataclasses.replace(settings, ai_provider="anthropic", anthropic_api_key="k")
    monkeypatch.setattr(ai, "settings", new)
    monkeypatch.setattr(ai_client, "settings", new)
    data = client.get("/api/ai/status").json()
    assert data == {**data, "local": False, "needs_consent": True, "ready": True, "model": "claude-haiku-5-5"}


def test_requests_fail_clearly_when_ai_is_off(monkeypatch):
    off = dataclasses.replace(settings, ai_provider="off")
    monkeypatch.setattr(ai, "settings", off)
    monkeypatch.setattr(ai_client, "settings", off)
    headers = upload()
    r = client.post("/api/ai/plan", json={"request": "remove duplicates"}, headers=headers)
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_unavailable"


# ----------------------------------------------------------------- plan

def test_plan_returns_only_valid_steps(use_ai):
    fake = use_ai({"reply": "Done", "steps": [
        step("remove_duplicates"),
        step("clean_email", columns=["email"]),
        step("trim_whitespace", columns=["salary"]),            # column does not exist
        step("delete_everything"),                              # not an operation
        {"operation": "standardize_text", "settings": "{not json", "reason": "x"},
        step("standardize_text", columns=["city"], case="shout"),  # invalid option
        {"operation": "run_python", "settings": json.dumps({"code": "import os"}), "reason": "x"},
    ]})
    headers = upload()
    r = client.post("/api/ai/plan", json={"request": "duplicates hatao aur emails saaf karo"}, headers=headers)
    assert r.status_code == 200, r.text
    data = R.AiPlan.model_validate(r.json())
    assert [s.operation["type"] for s in data.steps] == ["remove_duplicates", "clean_email"]
    assert len(data.rejected) == 5
    assert any("salary" in x.reason for x in data.rejected)
    # The data description was sent, not the file: no row is repeated as-is.
    prompt = fake.calls[0]["prompt"]
    assert '"email": text' in prompt and "duplicates hatao" in prompt
    assert "Ali Khan, ALI@GMAIL.COM ,Lhr" not in prompt
    # Nothing was changed.
    info = client.get("/api/session", headers=headers).json()
    assert info["history"] == [] and info["current_shape"]["rows"] == 5


def test_plan_steps_can_be_previewed_and_applied(use_ai):
    use_ai({"reply": "ok", "steps": [step("remove_duplicates"), step("clean_email", columns=["email"])]})
    headers = upload()
    plan = client.post("/api/ai/plan", json={"request": "clean it"}, headers=headers).json()
    ops = [s["operation"] for s in plan["steps"]]
    preview = client.post("/api/quick-clean/preview", json={"operations": ops}, headers=headers).json()
    assert preview["rows_after"] == 4
    applied = client.post("/api/quick-clean/apply", json={"operations": ops, "preview_token": preview["preview_token"]},
                          headers=headers)
    assert applied.status_code == 200 and applied.json()["applied"] == 2


def test_later_step_can_use_a_column_created_earlier(use_ai):
    use_ai({"reply": "", "steps": [
        step("split_column", column="name", names=["first", "last"]),
        step("standardize_text", columns=["first"], case="upper"),
    ]})
    data = client.post("/api/ai/plan", json={"request": "split names"}, headers=upload()).json()
    assert len(data["steps"]) == 2 and data["rejected"] == []


def test_settings_given_as_object_are_accepted(use_ai):
    use_ai({"reply": "", "steps": [{"operation": "remove_duplicates", "settings": {"keep": "last", "type": "x"}, "reason": ""}]})
    data = client.post("/api/ai/plan", json={"request": "dupes"}, headers=upload()).json()
    assert data["steps"][0]["operation"] == {"type": "remove_duplicates", "keep": "last"}


def test_values_are_not_shared_when_turned_off(use_ai):
    fake = use_ai({"reply": "", "steps": []}, ai_send_values=False)
    data = client.post("/api/ai/plan", json={"request": "clean"}, headers=upload()).json()
    prompt = fake.calls[0]["prompt"]
    assert "examples" not in prompt and "Lhr" not in prompt and "gmail" not in prompt
    assert "example values" not in data["shared"]


def test_plan_schema_follows_structured_output_rules():
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
            for bad in ("minLength", "maxLength", "minimum", "maximum"):
                assert bad not in node
            for v in node.values():
                check(v)
        elif isinstance(node, list):
            for v in node:
                check(v)
    for schema in (ai.PLAN_SCHEMA, ai.MAP_SCHEMA, ai.SUMMARY_SCHEMA):
        check(schema)


def test_operation_guide_lists_every_operation():
    guide = ai.operation_guide()
    for name in ai.OPERATION_MODELS:
        assert f"- {name}:" in guide
    assert '"national" | "international" | "e164"' in guide


# ----------------------------------------------------------------- consent and limits

def test_cloud_ai_needs_consent(use_ai):
    fake = use_ai({"reply": "", "steps": []}, provider="anthropic")
    headers = upload()
    r = client.post("/api/ai/plan", json={"request": "clean"}, headers=headers)
    assert r.status_code == 400 and r.json()["error"]["code"] == "ai_consent_required"
    assert fake.calls == []  # nothing was sent
    r = client.post("/api/ai/plan", json={"request": "clean", "consent": True}, headers=headers)
    assert r.status_code == 200


def test_request_limit_per_file(use_ai):
    use_ai({"reply": "", "steps": []}, ai_max_calls_per_session=2)
    headers = upload()
    codes = [client.post("/api/ai/plan", json={"request": "clean"}, headers=headers).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_sessions_are_isolated(use_ai):
    use_ai({"reply": "", "steps": []})
    r = client.post("/api/ai/plan", json={"request": "clean"}, headers={"X-Session-Id": "nope.nope"})
    assert r.status_code == 404


def test_request_text_is_validated(use_ai):
    use_ai({"reply": "", "steps": []})
    headers = upload()
    assert client.post("/api/ai/plan", json={"request": "  "}, headers=headers).status_code == 422
    assert client.post("/api/ai/plan", json={"request": "x" * 2001}, headers=headers).status_code == 422


# ----------------------------------------------------------------- value mapping

def test_map_values_keeps_only_real_changes(use_ai):
    fake = use_ai({"mappings": [
        {"value": "Lhr", "to": "Lahore"},
        {"value": "lahore", "to": "Lahore"},
        {"value": "LAHORE", "to": "Lahore"},
        {"value": "Karachi", "to": "Karachi"},     # no change
        {"value": "Islamabad", "to": "Isb"},       # not in the column
        {"value": "Lhr", "to": "Lahore city"},     # duplicate
        {"value": "lahore", "to": "  "},           # empty
    ]})
    r = client.post("/api/ai/map-values", json={"column": "city"}, headers=upload())
    data = R.AiMappings.model_validate(r.json())
    assert [(m.value, m.to) for m in data.mappings] == [("Lhr", "Lahore"), ("lahore", "Lahore"), ("LAHORE", "Lahore")]
    assert '"Lhr": 1' in fake.calls[0]["prompt"] and data.checked == 4


def test_map_values_unknown_column(use_ai):
    use_ai({"mappings": []})
    r = client.post("/api/ai/map-values", json={"column": "nope"}, headers=upload())
    assert r.status_code == 404


def test_map_values_needs_value_sharing(use_ai):
    use_ai({"mappings": []}, ai_send_values=False)
    r = client.post("/api/ai/map-values", json={"column": "city"}, headers=upload())
    assert r.status_code == 400 and r.json()["error"]["code"] == "ai_values_off"


# ----------------------------------------------------------------- summary

def test_summary_uses_the_change_report(use_ai):
    fake = use_ai({"summary": "We removed 1 duplicate row."})
    headers = upload()
    client.post("/api/operations/apply", json={"operation": {"type": "remove_duplicates"},
                                                "preview_token": client.post("/api/operations/preview",
                                                                             json={"operation": {"type": "remove_duplicates"}},
                                                                             headers=headers).json().get("preview_token")},
                headers=headers)
    r = client.post("/api/ai/summary", json={"language": "Urdu"}, headers=headers)
    data = R.AiSummary.model_validate(r.json())
    assert data.summary.startswith("We removed")
    assert "Rows: 5 before, 4 after" in fake.calls[0]["prompt"] and "Urdu" in fake.calls[0]["system"]


def _dedupe(headers):
    op = {"type": "remove_duplicates"}
    token = client.post("/api/operations/preview", json={"operation": op}, headers=headers).json().get("preview_token")
    client.post("/api/operations/apply", json={"operation": op, "preview_token": token}, headers=headers)


def test_summary_gets_the_totals_from_the_app(use_ai):
    fake = use_ai({"summary": "We removed 1 duplicate row."})
    headers = upload()
    _dedupe(headers)
    data = client.post("/api/ai/summary", json={}, headers=headers).json()
    assert "Totals: 1 steps, 0 cells changed, 1 rows removed, 0 columns removed." in fake.calls[0]["prompt"]
    assert data["note"] is None and len(fake.calls) == 1


def test_summary_with_invented_numbers_is_asked_again_then_replaced(use_ai):
    fake = use_ai({"summary": "We replaced 15 values and removed 1 duplicate."})
    headers = upload()
    _dedupe(headers)
    data = client.post("/api/ai/summary", json={}, headers=headers).json()
    assert len(fake.calls) == 2 and "15" in fake.calls[1]["prompt"]
    assert data["summary"].startswith("Hi! Your cleaned file is attached.")  # the exact change report
    assert "did not match" in data["note"]


def test_summary_retry_that_fixes_the_numbers_is_used(use_ai):
    fake = use_ai({"summary": "We replaced 15 values."})
    answers = iter([{"summary": "We replaced 15 values."}, {"summary": "We removed 1 duplicate row."}])
    fake.complete_json = lambda system, prompt, schema, max_tokens=2000: (
        fake.calls.append({"prompt": prompt}) or next(answers))
    headers = upload()
    _dedupe(headers)
    data = client.post("/api/ai/summary", json={}, headers=headers).json()
    assert data["summary"] == "We removed 1 duplicate row." and data["note"] is None


@pytest.mark.parametrize("text,numbers", [
    ("Removed 1,250 rows and 3.50 cells", {"1250", "3.5"}),
    ("1. Removed 4 rows\n2. Fixed 2 emails", {"4", "2"}),
    ("۱۵ قطاریں", {"15"}),
    ("No numbers here.", set()),
])
def test_numbers_in(text, numbers):
    assert ai.numbers_in(text) == numbers


def test_empty_summary_is_an_error(use_ai):
    use_ai({"summary": "  "})
    r = client.post("/api/ai/summary", json={}, headers=upload())
    assert r.status_code == 502


# ----------------------------------------------------------------- real clients (network replaced)

def test_ollama_client_sends_schema_and_parses_fenced_json(monkeypatch):
    sent = {}

    def fake_post(url, body, headers, timeout):
        sent.update(url=url, body=body)
        return {"message": {"content": '```json\n{"summary": "hi"}\n```'}}

    monkeypatch.setattr(ai_client, "_post_json", fake_post)
    out = ai_client.OllamaClient("qwen2.5:3b", "http://localhost:11434", 5).complete_json("s", "p", {"type": "object"})
    assert out == {"summary": "hi"}
    assert sent["url"].endswith("/api/chat") and sent["body"]["format"] == {"type": "object"}
    assert sent["body"]["options"]["temperature"] == 0 and sent["body"]["stream"] is False


def test_ollama_not_running_gives_a_helpful_error(monkeypatch):
    def refuse(*_a, **_k):
        raise urllib.error.URLError(ConnectionRefusedError())

    monkeypatch.setattr(ai_client, "_post_json", refuse)
    with pytest.raises(ai_client.AppError) as err:
        ai_client.OllamaClient("m", "http://localhost:11434", 5).complete_json("s", "p", {})
    assert err.value.code == "ai_unavailable" and "ollama.com" in err.value.hint


def test_anthropic_client_uses_structured_outputs(monkeypatch):
    sent = {}

    def fake_post(url, body, headers, timeout):
        sent.update(url=url, body=body, headers=headers)
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"summary": "ok"}'}]}

    monkeypatch.setattr(ai_client, "_post_json", fake_post)
    out = ai_client.AnthropicClient("claude-haiku-5-5", "key", 5).complete_json("sys", "p", {"type": "object"})
    assert out == {"summary": "ok"}
    assert sent["body"]["output_config"] == {"format": {"type": "json_schema", "schema": {"type": "object"}}}
    assert sent["headers"]["x-api-key"] == "key" and sent["body"]["system"] == "sys"


def test_unreadable_answer_is_an_error():
    with pytest.raises(ai_client.AppError) as err:
        ai_client._parse("Sure! Here is your plan")
    assert err.value.code == "ai_bad_answer"


# ----------------------------------------------------------------- chat with your data

ASK_PLAN = {"possible": True, "reply": "", "description": "Customers per city", "filters": [], "group_by": ["city"],
            "metric": "count_rows", "metric_column": "", "sort": "desc", "limit": 20}


def test_ask_computes_the_answer_from_the_data(use_ai):
    fake = use_ai(ASK_PLAN)
    headers = upload()
    r = client.post("/api/ai/ask", json={"question": "kis city mein sab se zyada customers hain?"}, headers=headers)
    assert r.status_code == 200, r.text
    data = R.AiAnswer.model_validate(r.json())
    assert data.possible and data.rows[0] == ["lahore", 2]
    assert data.answer == "Customers per city: lahore (2)" and data.steps[0] == "Group by city"
    assert "kis city" in fake.calls[0]["prompt"]
    assert client.get("/api/session", headers=headers).json()["history"] == []  # nothing changed


def test_ask_when_the_table_cannot_answer(use_ai):
    use_ai({**ASK_PLAN, "possible": False, "reply": "There is no sales column."})
    data = client.post("/api/ai/ask", json={"question": "what will sales be next year?"}, headers=upload()).json()
    assert data["possible"] is False and data["answer"] == "There is no sales column." and data["rows"] == []


def test_ask_refuses_a_plan_with_unknown_columns(use_ai):
    use_ai({**ASK_PLAN, "group_by": ["salary"]})
    r = client.post("/api/ai/ask", json={"question": "salary per city"}, headers=upload())
    assert r.status_code == 422 and r.json()["error"]["code"] == "ai_bad_plan"


def test_local_model_gets_a_shorter_prompt(use_ai):
    compact = ai.operation_guide(compact=True)
    assert len(compact) < len(ai.operation_guide()) * 0.8
    for name in ai.OPERATION_MODELS:
        assert f"- {name} (" in compact
    assert "format?:national|international|e164=international" in compact
    fake = use_ai({"reply": "", "steps": []})
    client.post("/api/ai/plan", json={"request": "clean"}, headers=upload())
    assert compact in fake.calls[0]["system"]


def test_code_like_reply_is_replaced(use_ai):
    use_ai({"reply": "remove_duplicates(keep?:first|last=first), clean_email(columns?:[email])",
            "steps": [step("remove_duplicates")]})
    data = client.post("/api/ai/plan", json={"request": "dupes hatao"}, headers=upload()).json()
    assert data["reply"].startswith("Here is a plan with 1 step.")


def test_prompt_contains_a_worked_example():
    import json as _json

    example = ai.PLAN_SYSTEM.format(guide="G", max_steps=10).split("Answer:\n")[1]
    parsed = _json.loads(example)
    for s in parsed["steps"]:
        ai.OPERATION.validate_python({"type": s["operation"], **_json.loads(s["settings"])})


def test_map_values_fixes_wrong_capitals_from_the_model(use_ai):
    body = "city\nIslamabad\nIslamabad\nISLAMABAD\nlahore\nLahore\nkarachi\nKarachi\nIsb\n"
    use_ai({"mappings": [{"value": "Islamabad", "to": "ISLAMABAD"}, {"value": "Isb", "to": "ISLAMABAD"}]})
    data = client.post("/api/ai/map-values", json={"column": "city"}, headers=upload(body)).json()
    got = {m["value"]: m["to"] for m in data["mappings"]}
    assert got == {"Isb": "Islamabad", "ISLAMABAD": "Islamabad", "lahore": "Lahore", "karachi": "Karachi"}


def test_map_values_suggests_title_case_when_no_proper_spelling_exists(use_ai):
    use_ai({"mappings": []})
    data = client.post("/api/ai/map-values", json={"column": "city"}, headers=upload("city\nlahore\nLAHORE\nKarachi\nAB12\nab12\n")).json()
    got = {m["value"]: m["to"] for m in data["mappings"]}
    assert got["lahore"] == "Lahore" and got["LAHORE"] == "Lahore"
    assert "AB12" not in got or got["AB12"] in ("AB12", "ab12")  # codes are not title-cased
