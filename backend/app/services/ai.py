"""AI assistant: turns plain-language requests into the app's own cleaning operations.

Safety design (the important part):

1. The model never runs code and never sees the whole file. It receives a short
   description of the data (column names, types, counts and, if allowed, a few example
   values per column) and must answer with JSON that matches a fixed schema.
2. Every operation it proposes is validated with the same Pydantic models the normal
   API uses, and tried on a sample of the data. Anything invalid is dropped and the
   user is told why.
3. Nothing changes until the user has seen the preview and pressed Apply. Applying
   goes through the normal Quick Clean endpoints, so every step can be undone.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
from pydantic import TypeAdapter, ValidationError

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.operations import OPERATION_MODELS, Operation
from app.services import ai_client, workspace
from app.services.operations import LABELS, run_operation
from app.services.sessions import Session

OPERATION = TypeAdapter(Operation)
MAX_STEPS = 10
SAMPLE_ROWS = 2000           # proposed steps are tried on this many rows before they are shown
MAX_PROMPT_COLUMNS = 150     # very wide files: describe the first 150 columns only
MAX_MAP_VALUES = 300         # value mapping: most frequent values sent to the model
LOCAL_EXAMPLES = 5           # local models read slowly on a CPU: fewer example values per column


# --------------------------------------------------------------------------- status and limits

def status() -> dict:
    info = ai_client.provider_info()
    enabled = info.provider != "off"
    ready: bool | None = enabled
    problem = None
    if info.provider == "ollama":
        installed = ai_client.OllamaClient(info.model, settings.ollama_url, 2).installed()
        ready = bool(installed)
        if installed is None:
            problem = "Ollama is not running. Install it from ollama.com and open it."
        elif not installed:
            problem = f"The model is not installed yet. In PowerShell run: ollama pull {info.model}"
    elif info.provider == "anthropic" and not settings.anthropic_api_key:
        ready, problem = False, "ANTHROPIC_API_KEY is missing in backend/.env."
    return {
        "enabled": enabled,
        "ready": bool(ready),
        "provider": info.provider,
        "model": info.model,
        "label": info.label,
        "local": info.local,
        "needs_consent": enabled and not info.local,
        "sends_values": settings.ai_send_values,
        "shared": _shared_text(values=settings.ai_send_values),
        "problem": problem,
    }


def _example_count() -> int:
    """Example values sent per column: fewer for a local model, which reads slowly on a CPU."""
    return min(LOCAL_EXAMPLES, settings.ai_max_values) if ai_client.provider_info().local else settings.ai_max_values


def _shared_text(values: bool) -> str:
    base = "Column names, column types and counts (rows, missing cells, different values)"
    if values:
        base += f", plus up to {_example_count()} example values per column"
    return base + ". The full file is never sent."


def _start(session: Session, consent: bool) -> ai_client.LLMClient:
    """Checks that apply to every AI request, then the client to use."""
    client = ai_client.get_client()
    if not ai_client.provider_info().local and not consent:
        raise AppError("ai_consent_required", "Please agree to send the data description to the cloud AI first.",
                       "Tick the box that says what will be shared, then try again.", status=400)
    limit = settings.ai_max_calls_per_session
    with session.lock:
        if limit and session.ai_calls >= limit:
            raise AppError("ai_limit", f"The AI assistant can be used {limit} times per file.",
                           "Use the cleaning steps directly, or upload the file again.", status=429)
        session.ai_calls += 1
    return client


# --------------------------------------------------------------------------- describing the data

def _type_text(schema: dict, defs: dict) -> str:
    if "$ref" in schema:
        sub = defs[schema["$ref"].split("/")[-1]]
        inner = "; ".join(f"{k}: {_type_text(v, defs)}" for k, v in sub["properties"].items())
        return "{" + inner + "}"
    if "anyOf" in schema:
        parts = [_type_text(s, defs) for s in schema["anyOf"] if s.get("type") != "null"]
        return " | ".join(parts) + " | null"
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    if schema.get("type") == "array":
        return f"list of {_type_text(schema.get('items', {}), defs)}"
    return schema.get("type", "any")


def operation_guide(compact: bool = False) -> str:
    """One line per operation with its fields, generated from the real Pydantic models.

    compact=True leaves out the field descriptions: about a third of the length, which matters
    for a local model on a laptop CPU, where reading the prompt is the slowest part.
    """
    if compact:
        return "\n".join(_compact_line(name, model) for name, model in OPERATION_MODELS.items())
    lines = []
    for name, model in OPERATION_MODELS.items():
        schema = model.model_json_schema()
        defs = schema.get("$defs", {})
        required = set(schema.get("required", []))
        fields = []
        for field, spec in schema["properties"].items():
            if field == "type":
                continue
            text = f"{field}: {_type_text(spec, defs)}"
            if field not in required and "default" in spec:
                text += f" = {json.dumps(spec['default'])}"
            elif field in required:
                text += " (required)"
            if spec.get("description"):
                text += f" ({spec['description']})"
            fields.append(text)
        doc = (model.__doc__ or "").strip().splitlines()[0]
        lines.append(f"- {name}: {doc}\n    " + ("\n    ".join(fields) if fields else "no settings"))
    return "\n".join(lines)


def _compact_type(spec: dict, defs: dict) -> str:
    if "$ref" in spec:
        sub = defs[spec["$ref"].split("/")[-1]]
        return "{" + ",".join(f"{k}:{_compact_type(v, defs)}" for k, v in sub["properties"].items()) + "}"
    if "anyOf" in spec:
        return "|".join(_compact_type(s, defs) for s in spec["anyOf"] if s.get("type") != "null")
    if "enum" in spec:
        return "|".join(str(v) for v in spec["enum"])
    if spec.get("type") == "array":
        return f"[{_compact_type(spec.get('items', {}), defs)}]"
    return {"string": "text", "boolean": "bool", "integer": "int"}.get(spec.get("type", ""), spec.get("type", "any"))


def _compact_line(name: str, model) -> str:
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    required = set(schema.get("required", []))
    fields = []
    for field, spec in schema["properties"].items():
        if field == "type":
            continue
        text = f"{field}{'' if field in required else '?'}:{_compact_type(spec, defs)}"
        if "default" in spec and spec["default"] not in (None, [], ""):
            text += f"={spec['default']}"
        fields.append(text)
    doc = (model.__doc__ or "").strip().splitlines()[0].rstrip(".")
    return f"- {name} ({doc}): " + (", ".join(fields) if fields else "no settings")


def _examples(series: pd.Series, limit: int) -> list[str]:
    counts = series.dropna().astype(str).str.slice(0, 60).value_counts()
    return [str(v) for v in counts.head(limit).index]


def describe_data(session: Session, values: bool, examples: int | None = None) -> str:
    """A compact text description of the working data for the model."""
    with session.lock:
        df = session.current
        profile = workspace.get_profile(session)
    lines = [f"Rows: {len(df)}. Columns: {df.shape[1]}."]
    if df.shape[1] > MAX_PROMPT_COLUMNS:
        lines.append(f"(Only the first {MAX_PROMPT_COLUMNS} columns are described.)")
    for col in profile["columns"][:MAX_PROMPT_COLUMNS]:
        text = f'- "{col["name"]}": {col["type"]}, {col["missing"]} missing, {col["unique"]} different values'
        if values:
            shown = _examples(df[col["name"]], examples or settings.ai_max_values)
            if shown:
                text += f"; examples: {json.dumps(shown, ensure_ascii=False)}"
        lines.append(text)
    issues = [i["title"] for i in profile.get("issues", [])][: 12 if ai_client.provider_info().local else 30]
    if issues and values:  # issue titles can quote values from the file
        lines.append("Problems the app found:\n" + "\n".join(f"- {t}" for t in issues))
    return "\n".join(lines)


# --------------------------------------------------------------------------- 1. plain-language cleaning

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reply": {"type": "string", "description": "One or two short sentences for the user about the plan."},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "operation": {"type": "string", "enum": list(OPERATION_MODELS)},
                    "settings": {"type": "string", "description": "JSON object with this operation's settings."},
                    "reason": {"type": "string"},
                },
                "required": ["operation", "settings", "reason"],
            },
        },
    },
    "required": ["reply", "steps"],
}

PLAN_SYSTEM = """You are the assistant inside CleanData Studio, a data-cleaning app.
The user describes in plain language (often English, Urdu or Roman Urdu) how they want their table cleaned.
Turn the request into a short list of the app's operations, in the order they should run.

Rules:
- Use only these operations and only the settings listed for them:
{guide}
- "settings" must be a JSON object as a string, e.g. "{{\\"columns\\": [\\"email\\"]}}". Do not include "type".
- Use column names exactly as written in the data description. Never invent columns.
- Only do what the user asked: one step for each thing they asked for, nothing extra. Do not add steps
  for problems they did not mention. If something cannot be done with these operations, say so in "reply".
- Use only setting names listed for that operation; leave out settings you do not need (defaults are used).
- Prefer safe choices: keep values that cannot be fixed (on_invalid/on_error "keep" or "set_missing", never delete data the user did not ask to delete).
- At most {max_steps} steps. "reply" is one short, friendly sentence for the user in the language they wrote in;
  never put operation names or settings in "reply".

Example. Request: "remove duplicates and make city names title case" (the table has a "city" column). Answer:
{{"reply": "I will remove duplicate rows and write city names in Title Case.", "steps": [
 {{"operation": "remove_duplicates", "settings": "{{}}", "reason": "You asked to remove duplicates."}},
 {{"operation": "standardize_text", "settings": "{{\\"columns\\": [\\"city\\"], \\"case\\": \\"title\\"}}", "reason": "You asked for Title Case city names."}}]}}
"""


def _columns_in(op) -> list[str]:
    cols: list[str] = []
    for field in ("columns",):
        cols += list(getattr(op, field, None) or [])
    for field in ("column", "region_column"):
        value = getattr(op, field, None)
        if isinstance(value, str):
            cols.append(value)
    for field in ("drop", "order"):
        cols += list(getattr(op, field, None) or [])
    for item in [*(getattr(op, "rename", None) or []), *(getattr(op, "by", None) or [])]:
        cols.append(item.column)
    for rule in getattr(op, "rules", None) or []:
        cols.append(rule.column)
        if rule.region_column:
            cols.append(rule.region_column)
    return cols


def validate_steps(df: pd.DataFrame, raw_steps: list[dict]) -> tuple[list[dict], list[dict]]:
    """Turn the model's steps into real operations. Returns (accepted, rejected).

    Each step must be a valid operation, mention only columns that exist at that point,
    and run without error on a sample of the data (steps run in order, so a column
    created or renamed by an earlier step can be used by a later one).
    """
    accepted: list[dict] = []
    rejected: list[dict] = []
    work = df.head(SAMPLE_ROWS)
    for raw in raw_steps[:MAX_STEPS]:
        name = str(raw.get("operation", ""))
        label = LABELS.get(name, name or "Unknown step")
        try:
            params = raw.get("settings") or {}
            if isinstance(params, str):
                params = json.loads(params) if params.strip() else {}
            if not isinstance(params, dict):
                raise ValueError
            params.pop("type", None)
            op = OPERATION.validate_python({"type": name, **params})
        except (ValueError, ValidationError) as exc:
            reason = "its settings were not valid"
            if isinstance(exc, ValidationError) and exc.errors():
                err = exc.errors()[0]
                if err.get("type") == "union_tag_invalid":
                    reason = "it is not one of the app's cleaning operations"
                else:
                    where = ".".join(str(p) for p in err.get("loc", ())[1:]) or "settings"
                    reason = f"{where}: {err.get('msg', 'invalid')}"
            rejected.append({"label": label, "reason": reason})
            continue
        missing = [c for c in _columns_in(op) if c not in work.columns]
        if missing:
            rejected.append({"label": label, "reason": f'there is no column called "{missing[0]}"'})
            continue
        try:
            result = run_operation(work, op)
        except AppError as exc:
            rejected.append({"label": label, "reason": exc.message})
            continue
        if not result.blocked:
            work = result.df
        accepted.append({"operation": op.model_dump(mode="json"), "label": label, "reason": str(raw.get("reason", ""))[:300]})
    return accepted, rejected


_CODE_LIKE = re.compile(r"\?:|\w+\(|[{}\[\]]|_\w+=")


def _clean_reply(reply: object, steps: int) -> str:
    """The model's sentence for the user, or a plain one when a small model returned code-like text."""
    text = str(reply or "").strip()
    if not text or len(text) > 400 or len(_CODE_LIKE.findall(text)) >= 2:
        if not steps:
            return "I could not turn this into cleaning steps. Try naming the column and what should happen to it."
        return f"Here is a plan with {steps} step{'s' if steps != 1 else ''}. Untick anything you don't want, then preview."
    return text


def plan(session: Session, request: str, consent: bool = False) -> dict:
    client = _start(session, consent)
    values = settings.ai_send_values
    local = ai_client.provider_info().local
    system = PLAN_SYSTEM.format(guide=operation_guide(compact=local), max_steps=MAX_STEPS)
    prompt = f"Data description:\n{describe_data(session, values, _example_count())}\n\nUser request:\n{request}"
    answer = client.complete_json(system, prompt, PLAN_SCHEMA, max_tokens=2000)
    steps = answer.get("steps") if isinstance(answer.get("steps"), list) else []
    with session.lock:
        accepted, rejected = validate_steps(session.current, [s for s in steps if isinstance(s, dict)])
    return {
        "reply": _clean_reply(answer.get("reply"), len(accepted)),
        "steps": accepted,
        "rejected": rejected,
        "shared": _shared_text(values),
        "provider": ai_client.provider_info().label,
    }


# --------------------------------------------------------------------------- 2. value mapping (Lhr -> Lahore)

MAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"value": {"type": "string"}, "to": {"type": "string"}},
                "required": ["value", "to"],
            },
        },
    },
    "required": ["mappings"],
}

MAP_SYSTEM = """You standardise the values of one column of a table.
You get the column name and its different values with how often each appears.
Group values that mean the same thing: spelling mistakes, abbreviations, different letter case,
extra spaces or punctuation, local and English names (e.g. "Lhr", "lahore", "LAHORE" -> "Lahore").
For each group choose one correct, complete, properly capitalised form ("Islamabad", not "ISLAMABAD" or "islamabad").
Return only the values that should change, as {"value": original value exactly as given, "to": new value}.
Never merge values that are different things (e.g. two different cities or products). When unsure, leave the value out.

Example. Values: "Islamabad": 5, "ISB": 2, "isb": 1, "Karachi": 4, "khi": 1. Answer:
{"mappings": [{"value": "ISB", "to": "Islamabad"}, {"value": "isb", "to": "Islamabad"}, {"value": "khi", "to": "Karachi"}]}
"""


def suggest_mappings(session: Session, column: str, consent: bool = False) -> dict:
    if not settings.ai_send_values:
        raise AppError("ai_values_off", "Suggesting value mappings needs to send the column's values to the AI.",
                       "Set AI_SEND_VALUES=true in backend/.env, or fill the mapping table by hand.", status=400)
    values = workspace.get_values(session, column, limit=MAX_MAP_VALUES)  # also checks that the column exists
    client = _start(session, consent)
    listing = "\n".join(f"{json.dumps(v['value'], ensure_ascii=False)}: {v['count']}" for v in values["values"])
    prompt = f'Column: "{column}"\nValues (value: count):\n{listing}'
    answer = client.complete_json(MAP_SYSTEM, prompt, MAP_SCHEMA, max_tokens=3000)
    from app.services.quick_clean import best_spellings, well_cased

    counts = {v["value"]: v["count"] for v in values["values"]}
    # Differences in capitals and spaces only are decided by fixed rules, not by the model:
    # small models sometimes pick "ISLAMABAD" over "Islamabad" or miss some variants.
    best = best_spellings(counts)
    # When the file has no properly capitalised spelling of a word ("lahore", "LAHORE"),
    # a properly capitalised one from the model ("Lahore") is used instead.
    for m in answer.get("mappings") or []:
        to = str(m.get("to", "")).strip() if isinstance(m, dict) else ""
        key = to.lower()
        if to and well_cased(to) and not well_cased(best.get(key, next((v for v in counts if v.strip().lower() == key), ""))):
            best[key] = to

    for key, spelling in list(best.items()):
        # Still only "lahore"/"LAHORE": suggest Title Case for plain words. It is only a suggestion
        # in the mapping table, which the user reviews before anything is applied.
        if not well_cased(spelling) and re.fullmatch(r"[^\W\d_]+(?:[ '\-][^\W\d_]+)*", spelling.strip()):
            best[key] = spelling.strip().title()

    def proper(text: str) -> str:
        return best.get(text.strip().lower(), text)

    mappings, seen = [], set()
    for m in answer.get("mappings") or []:
        if not isinstance(m, dict):
            continue
        value, to = str(m.get("value", "")), proper(str(m.get("to", "")).strip())
        # Keep only real values of this column that actually change; ignore anything invented.
        if value in counts and to and to != value and value not in seen and len(to) <= 1000:
            if to.strip().lower() == value.strip().lower() and proper(value) == value:
                continue  # the model "corrected" a spelling that is already the right one
            seen.add(value)
            mappings.append({"value": value, "to": to})
    for value in counts:  # case and space variants the model did not mention
        to = proper(value)
        if to != value and value not in seen:
            seen.add(value)
            mappings.append({"value": value, "to": to})
    return {
        "column": column,
        "mappings": mappings[:1000],
        "checked": len(values["values"]),
        "truncated": values["truncated"],
        "shared": f'The {len(values["values"])} most common different values of "{column}" and how often each appears.',
        "provider": ai_client.provider_info().label,
    }


# --------------------------------------------------------------------------- 3. plain-language report

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}

SUMMARY_SYSTEM = """You write a short, friendly report for a client whose spreadsheet was cleaned.
Use plain language, no jargon, 4 to 8 short sentences or bullet points.
Say what problems were found, what was fixed (with numbers), and what still needs the client's decision.
Only use facts from the information given. Do not invent numbers. Write in {language}.
"""


def summary(session: Session, language: str = "English", consent: bool = False) -> dict:
    client = _start(session, consent)
    values = settings.ai_send_values
    report = workspace.change_report(session)
    lines = [
        f"File: {report['file']}",
        f"Rows: {report['rows_before']} before, {report['rows_after']} after. "
        f"Columns: {report['columns_before']} before, {report['columns_after']} after.",
        "Steps applied:",
    ]
    for s in report["steps"]:
        # Step summaries can quote values ("Lhr -> Lahore"); send only labels when values are off.
        lines.append(f"- {s['label']}: {s['summary']}" if values else f"- {s['label']}")
    if not report["steps"]:
        lines.append("- none yet")
    for r in report["review"]:
        lines.append(f'Needs review: {r["rows"]} rows in "{r["column"]}"')
    if values:
        lines += [f"Open item: {o}" for o in report["open_items"]]
    answer = client.complete_json(SUMMARY_SYSTEM.format(language=language), "\n".join(lines), SUMMARY_SCHEMA, max_tokens=1200)
    text = str(answer.get("summary", "")).strip()
    if not text:
        raise AppError("ai_bad_answer", "The AI did not write a summary.", "Try again.", status=502)
    return {"summary": text[:5000], "shared": "The change report: row and column counts and the list of applied steps.",
            "provider": ai_client.provider_info().label}


# --------------------------------------------------------------------------- 4. questions about the data

def ask(session: Session, question: str, consent: bool = False) -> dict:
    """Answer a question with a query plan from the model, computed by the app on the real data."""
    from app.services import ask as query

    client = _start(session, consent)
    values = settings.ai_send_values
    prompt = f"Data description:\n{describe_data(session, values, _example_count())}\n\nQuestion:\n{question}"
    raw = client.complete_json(query.SYSTEM, prompt, query.PLAN_SCHEMA, max_tokens=800)
    base = {"question": question, "shared": _shared_text(values), "provider": ai_client.provider_info().label}
    if not raw.get("possible", True):
        reply = str(raw.get("reply") or "This question cannot be answered from the table.")[:1000]
        return {**base, "possible": False, "answer": reply, "description": "", "steps": [], "columns": [], "rows": [],
                "total_groups": 0, "rows_matched": 0, "notes": []}
    with session.lock:
        df = session.current
        plan = query.check_plan(df, raw)
        result = query.run(df, plan)
    return {**base, "possible": True, "description": plan["description"], "steps": query.explain(plan), **result}
