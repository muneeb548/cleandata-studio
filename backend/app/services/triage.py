"""What to do about each detected issue: let the tool fix it, ask the client, or just note it.

Detection (profiling.py) only says what looks wrong. This layer adds the decision a person
would otherwise have to make for every line, using what has already been done to the file:

* "fix"    the right value is certain (spaces, capitals, "N/A", formats, duplicates): Fix.
* "client" fixing it would need a guess (a missing email, an address without "@", an age of
           250, a phone that is not a real number): mark it with Flag for review and ask.
* "info"   nothing is wrong (possible outliers, formula-like text, cells that are empty for a
           good reason such as rows without a match in a joined file).

It also marks issues already covered by a "Flag rows for review" step, hides columns the app
created itself (a review column is empty for rows without a problem) and separates the issues
the user marked as reviewed. Similar to "needs review / confirmed / hidden" lists in
accessibility checkers and "resolve with a note" in data quality platforms.
"""

from __future__ import annotations

import copy
import time

FIX_KINDS = {"duplicates", "empty_rows", "empty_col", "whitespace", "blank", "placeholder", "case", "dates",
             "mixed", "countries", "amounts", "column_names"}
INFO_KINDS = {"outliers", "formula", "no_rows"}
# Flag checks that cover an issue kind.
FLAG_COVERS = {"missing": "missing", "emails": "invalid_email", "phones": "invalid_phone", "outliers": "out_of_range",
               "mixed": "not_number"}

ACTION_TEXT = {
    "fix": "The tool can fix this: the right value is certain.",
    "client": "Fixing this would need a guess. Mark these rows with Flag for review and ask your client.",
    "info": "Nothing is wrong here; it is shown so you know about it.",
}


def _kind(issue: dict) -> str:
    return issue["id"].split(":", 1)[0]


def _step_columns(params: dict) -> set[str]:
    cols = set(params.get("columns") or [])
    if isinstance(params.get("column"), str):
        cols.add(params["column"])
    return cols


def _history_facts(session) -> dict:
    applied: dict[str, set[str]] = {}       # operation type -> columns it touched
    flagged: dict[tuple[str, str], str] = {}  # (column, check) -> review column name
    own_columns: set[str] = set()            # columns the app created (review / group columns)
    joined: dict[str, str] = {}              # column brought by a join -> file name
    for h in session.history:
        p = h.params
        applied.setdefault(h.type, set()).update(_step_columns(p))
        if h.type == "flag_rows":
            own_columns.add(p.get("column_name", "needs_review"))
            for rule in p.get("rules", []):
                flagged[(rule["column"], rule["check"])] = p.get("column_name", "needs_review")
        elif h.type == "near_duplicates" and p.get("action") == "flag":
            own_columns.add(p.get("column_name", "duplicate_group"))
        elif h.type == "combine_files" and p.get("mode") == "join":
            attached = session.files.get(p.get("file_id"))
            if attached is not None:
                keys = {k["right"] for k in p.get("keys", [])}
                brought = p.get("columns") or [c for c in map(str, attached.df.columns) if c not in keys]
                for c in brought:
                    joined[c] = attached.name
                    joined[f"{c}{p.get('suffix', '_2')}"] = attached.name
        elif h.type == "combine_files" and p.get("source_column"):
            own_columns.add(p["source_column"])
    return {"applied": applied, "flagged": flagged, "own": own_columns, "joined": joined}


def _decide(issue: dict, facts: dict) -> tuple[str, str | None]:
    """(action, suggested reason for "Mark as reviewed")."""
    kind, col = _kind(issue), issue.get("column")
    applied = facts["applied"]
    if kind in FIX_KINDS:
        return "fix", None
    if kind in INFO_KINDS:
        if kind == "outliers":
            return "info", "Checked: these values are real."
        if kind == "formula":
            return "info", "Delivered as Excel, where these values are always kept as text."
        return "info", None
    if kind == "missing":
        if col in facts["joined"]:
            return "info", f'These rows had no match in "{facts["joined"][col]}".'
        return "client", "Not given in the original file, so left empty."
    if kind == "emails":
        # Before "Clean email addresses" the tool can still tidy them; after it, what is left are
        # addresses that cannot be real (no "@"), which only the client can correct.
        if col in applied.get("clean_email", set()):
            return "client", "Could not be fixed without guessing; marked for review."
        return "fix", None
    if kind == "phones":
        if col in applied.get("standardize_phone", set()):
            return "client", "These are not real numbers for their country; marked for review."
        return "fix", None
    return "fix", None


def annotate(profile: dict, session) -> dict:
    """A copy of a full profile with action, flagged_in and reviewed applied to its issues."""
    out = copy.copy(profile)
    facts = _history_facts(session)
    reviewed = session.reviewed
    issues, done = [], []
    for raw in profile.get("issues", []):
        issue = dict(raw)
        if issue.get("column") in facts["own"] and _kind(issue) == "missing":
            continue  # a review column is empty for rows without a problem: that is the point
        action, reason = _decide(issue, facts)
        if _kind(issue) == "phones" and action == "client":
            issue["title"] = f'Phone numbers that are not real numbers in "{issue["column"]}"'
            issue["description"] = ("They were kept as they are because they are not valid for their country. "
                                    "Mark them with Flag for review so your client can send the right numbers.")
            issue["suggested_operation"] = "flag_rows"
        if _kind(issue) == "emails" and action == "client":
            issue["suggested_operation"] = "flag_rows"
        if action == "client" and _kind(issue) == "missing":
            issue["suggested_operation"] = "flag_rows"
        check = FLAG_COVERS.get(_kind(issue))
        flagged_in = facts["flagged"].get((issue.get("column"), check)) if check else None
        issue["action"] = action
        issue["action_text"] = ACTION_TEXT[action]
        issue["suggested_reason"] = reason
        issue["flagged_in"] = flagged_in
        if issue["id"] in reviewed:
            done.append({**reviewed[issue["id"]], "id": issue["id"], "title": issue["title"], "still_open": True})
            continue
        issues.append(issue)
    present = {d["id"] for d in done}
    for issue_id, item in reviewed.items():
        if issue_id not in present:
            done.append({**item, "id": issue_id, "still_open": False})
    order = {"fix": 0, "client": 1, "info": 2}
    issues.sort(key=lambda i: (order[i["action"]], i["flagged_in"] is not None))
    counts = {k: sum(1 for i in issues if i["action"] == k) for k in order}
    out["issues"] = issues
    out["reviewed"] = sorted(done, key=lambda d: d.get("at", 0))
    # The health summary and per-column problem counts follow the same decision: only what the
    # tool can still fix makes the data "need cleaning"; the app's own columns are not problems.
    if out.get("health"):
        per_column: dict[str, int] = {}
        for i in issues:
            if i["action"] != "info" and i.get("column"):
                per_column[i["column"]] = per_column.get(i["column"], 0) + 1
        out["columns"] = [{**c, "issues": per_column.get(c["name"], 0)} for c in out.get("columns", [])]
        out["health"] = {**out["health"], "issues": counts["fix"], "notes": counts["client"] + counts["info"],
                         "columns_with_issues": len({i["column"] for i in issues if i["action"] == "fix" and i.get("column")}),
                         "needs_cleaning": counts["fix"] > 0}
    out["triage"] = {
        **counts,
        "flagged": sum(1 for i in issues if i["flagged_in"]),
        "reviewed": len(done),
        "client_open": sum(1 for i in issues if i["action"] == "client" and not i["flagged_in"]),
    }
    return out


def review(session, issue: dict, reason: str) -> None:
    session.reviewed[issue["id"]] = {"title": issue["title"], "reason": reason.strip(), "at": time.time(),
                                     "column": issue.get("column"), "count": issue.get("count")}


def unreview(session, issue_id: str) -> bool:
    return session.reviewed.pop(issue_id, None) is not None
