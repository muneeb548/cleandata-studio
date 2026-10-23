"""Issue labels (tool can fix / needs your client / information) and Mark as reviewed."""

import pytest
from pydantic import TypeAdapter

from app.core.errors import AppError
from app.schemas import responses as R
from app.schemas.operations import Operation
from app.services import workspace
from app.services.sessions import SessionStore

from .conftest import preview_apply

OP = TypeAdapter(Operation)
CSV = (
    "id,name,email,age,city\n"
    "1, Ali ,ALI@x.com,25,Lahore\n"
    "2,Sara,saragmail.com,250,lahore\n"
    "3,Omar,,31,\n"
    "4,Zoya,zoya@x.com,N/A,Karachi\n"
    "5,Hina,hina@x.com,28,Karachi\n"
    "6,Bilal,bilal@x.com,30,Lahore\n"
)
TIERS = "email,tier\nali@x.com,Gold\n"


@pytest.fixture
def session():
    store = SessionStore(ttl_seconds=600, max_sessions=10)
    return store.get(workspace.create_session(store, "c.csv", CSV.encode())["session_id"]), store


def issues(s):
    return {i["id"]: i for i in workspace.get_profile(s)["issues"]}


def run(s, **op):
    preview_apply(s, OP.validate_python(op))


def test_labels_before_any_cleaning(session):
    s, _ = session
    found = issues(s)
    assert found["whitespace:name"]["action"] == "fix"
    assert found["placeholder:age"]["action"] == "fix"
    assert found["case:city"]["action"] == "fix"
    assert found["emails:email"]["action"] == "fix"      # tidy first
    assert found["missing:email"]["action"] == "client"  # an email cannot be invented
    assert found["missing:email"]["suggested_operation"] == "flag_rows"
    profile = workspace.get_profile(s)
    R.Profile.model_validate(profile)
    assert profile["triage"]["fix"] >= 4 and profile["triage"]["client"] >= 1
    # Fix items come first.
    actions = [i["action"] for i in profile["issues"]]
    assert actions == sorted(actions, key=["fix", "client", "info"].index)


def test_after_cleaning_emails_the_rest_needs_the_client(session):
    s, _ = session
    run(s, type="clean_email", columns=["email"])
    e = issues(s)["emails:email"]
    assert e["action"] == "client" and e["suggested_operation"] == "flag_rows"


def test_flag_step_marks_issues_as_flagged_and_hides_its_own_column(session):
    s, _ = session
    run(s, type="clean_email", columns=["email"])
    run(s, type="flag_rows", column_name="needs_review",
        rules=[{"column": "email", "check": "missing"}, {"column": "email", "check": "invalid_email"}])
    found = issues(s)
    assert found["missing:email"]["flagged_in"] == "needs_review"
    assert found["emails:email"]["flagged_in"] == "needs_review"
    assert "missing:needs_review" not in found  # empty = no problem in that row
    assert workspace.get_profile(s)["triage"]["client_open"] == 1  # only "city" is not flagged yet


def test_missing_after_a_join_is_information(session):
    s, store = session
    fid = workspace.attach_file(store, s, "tiers.csv", TIERS.encode())["file"]["id"]
    run(s, type="clean_email", columns=["email"])
    run(s, type="combine_files", file_id=fid, mode="join", keys=[{"left": "email", "right": "email"}])
    tier = issues(s)["missing:tier"]
    assert tier["action"] == "info" and "tiers.csv" in tier["suggested_reason"]


def test_mark_as_reviewed_moves_it_and_reaches_the_report(session):
    s, _ = session
    res = workspace.review_issue(s, "missing:city", "Not given by the client.")
    R.ReviewedList.model_validate(res)
    profile = workspace.get_profile(s)
    assert "missing:city" not in {i["id"] for i in profile["issues"]}
    assert profile["reviewed"][0]["reason"] == "Not given by the client." and profile["reviewed"][0]["still_open"]
    report = workspace.change_report(s)
    R.ChangeReport.model_validate(report)
    assert "Checked and left as they are:" in report["message"]
    assert '1 missing value in "city": Not given by the client.' in report["message"]
    workspace.unreview_issue(s, "missing:city")
    assert "missing:city" in issues(s)
    assert "Checked and left" not in workspace.change_report(s)["message"]


def test_review_needs_a_reason_and_a_real_issue(session):
    s, _ = session
    with pytest.raises(AppError) as err:
        workspace.review_issue(s, "missing:city", "  ")
    assert err.value.code == "reason_required"
    with pytest.raises(AppError) as err:
        workspace.review_issue(s, "nope", "x")
    assert err.value.code == "issue_not_found"
    with pytest.raises(AppError):
        workspace.unreview_issue(s, "missing:city")


def test_reviewed_issue_that_is_later_fixed_stays_in_the_list(session):
    s, _ = session
    workspace.review_issue(s, "whitespace:name", "Fine.")
    run(s, type="trim_whitespace")
    reviewed = workspace.get_profile(s)["reviewed"]
    assert reviewed[0]["id"] == "whitespace:name" and reviewed[0]["still_open"] is False


def test_original_dataset_gets_labels_without_reviews(session):
    s, _ = session
    workspace.review_issue(s, "missing:city", "Not given.")
    original = workspace.get_profile(s, "original")
    assert "missing:city" in {i["id"] for i in original["issues"]} and original["reviewed"] == []


def test_reviews_are_saved_with_the_session(tmp_path):
    store = SessionStore(ttl_seconds=0, max_sessions=10, saved_dir=str(tmp_path))
    token = workspace.create_session(store, "c.csv", CSV.encode())["session_id"]
    workspace.review_issue(store.get(token), "missing:city", "Not given.")
    again = SessionStore(ttl_seconds=0, max_sessions=10, saved_dir=str(tmp_path)).get(token)
    assert again.reviewed["missing:city"]["reason"] == "Not given."


def test_phones_after_standardising_need_the_client():
    pytest.importorskip("phonenumbers")
    store = SessionStore(ttl_seconds=600, max_sessions=10)
    csv = "name,country,phone\nAli,Pakistan,0300-1234567\nSara,UK,07911 123456\nOmar,UAE,0593443916\n"
    s = store.get(workspace.create_session(store, "p.csv", csv.encode())["session_id"])
    assert issues(s)["phones:phone"]["action"] == "fix"
    run(s, type="standardize_phone", columns=["phone"], region="US", region_column="country")
    phone = issues(s).get("phones:phone")
    # Only the number that is not real for its country is left, and it is for the client.
    assert phone is not None and phone["action"] == "client" and phone["suggested_operation"] == "flag_rows"
    assert "not real numbers" in phone["title"]
