

import json
import re
from dataclasses import dataclass
from typing import Callable

CODE_RE = re.compile(r"\b[A-Z]{2,5}-\d{2,3}[A-Z]?\b")
INSTRUCTOR_RE = re.compile(r"Dr\. [A-Z][a-z]+ [A-Z][a-z]+")
SEATS_RE = re.compile(r"(\d+)\s+(?:available\s+)?seats", re.IGNORECASE)


@dataclass
class Check:
    passed: bool
    assertion: str = ""       # the first assertion that failed (empty on success)
    evidence: str = ""        # the tool call / observation that shows it


def _obs(call: dict) -> dict:
    try:
        return json.loads(call["observation"])
    except (ValueError, TypeError, KeyError):
        return {"ok": False, "data": None, "error": "unparseable observation"}


def _ok_calls(result: dict, tool: str) -> list[dict]:
    return [c for c in result["tool_calls"] if c["tool"] == tool and c["ok"]]


def _has(answer: str, *needles: str) -> list[str]:
    """Needles that are missing from the answer (case-insensitive)."""
    low = (answer or "").lower()
    return [n for n in needles if str(n).lower() not in low]


def verify_a(result: dict) -> Check:
    """Search for a term, then look up the FIRST search result and report it."""
    searches = _ok_calls(result, "search_courses")
    if not searches:
        return Check(False, "search_courses was called successfully", "no successful search_courses call in the trace")
    rows = _obs(searches[0])["data"]["courses"]
    if not rows:
        return Check(False, "the search returned at least one course", f"search {searches[0]['input']} returned 0 rows")
    first = rows[0]
    detail_calls = [c for c in _ok_calls(result, "course_detail") if c["input"].get("course_id") == first["id"]]
    if not detail_calls:
        ids = [c["input"].get("course_id") for c in result["tool_calls"] if c["tool"] == "course_detail"]
        return Check(False, "course_detail was called with the id of the first search result", f"first result id={first['id']}, detail calls used ids {ids}")
    detail = _obs(detail_calls[0])["data"]
    missing = _has(result["answer"], detail["courseCode"], detail["instructor"]["name"])
    if missing:
        return Check(False, "the answer states the course code and instructor", f"answer is missing {missing}")
    return Check(True)


def verify_b(result: dict) -> Check:
    """Aggregate question (department with the most seats), then one supporting example."""
    stats = [c for c in _ok_calls(result, "course_stats") if c["input"].get("group_by") == "department"]
    if not stats:
        return Check(False, "course_stats(group_by='department') was called", "no successful department aggregate in the trace")
    groups = _obs(stats[0])["data"]["groups"]
    top = max(groups, key=lambda g: g["totalSeats"])
    later = [c for c in result["tool_calls"][result["tool_calls"].index(stats[0]) + 1:] if c["ok"] and c["tool"] in ("search_courses", "course_detail")]
    examples = []
    for c in later:
        data = _obs(c)["data"]
        rows = data["courses"] if c["tool"] == "search_courses" else [data]
        examples += [r for r in rows if r.get("department") == top["group"]]
    if not examples:
        return Check(False, "a supporting example from the top department was retrieved",
                     f"top department is {top['group']} ({top['totalSeats']} seats); no later search/detail returned one of its courses")
    missing = _has(result["answer"], top["group"])
    if missing:
        return Check(False, "the answer names the department with the most seats", f"expected {top['group']}; answer is missing it")
    if not any(e["courseCode"].lower() in result["answer"].lower() or e["courseTitle"].lower() in result["answer"].lower() for e in examples):
        return Check(False, "the answer cites a retrieved course from that department", f"none of {[e['courseCode'] for e in examples]} appears in the answer")
    return Check(True)


def verify_c(result: dict) -> Check:
    """Compare two named courses: one search plus two detail lookups, then a grounded comparison."""
    if not _ok_calls(result, "search_courses"):
        return Check(False, "search_courses was called", "no successful search_courses call in the trace")
    details = {}
    for c in _ok_calls(result, "course_detail"):
        d = _obs(c)["data"]
        details[d["courseTitle"]] = d
    wanted = {"Machine Learning Foundations", "Database Systems"}
    if not wanted <= set(details):
        return Check(False, "course_detail was called for both named courses", f"detail lookups cover {sorted(details)}; missing {sorted(wanted - set(details))}")
    a, b = details["Machine Learning Foundations"], details["Database Systems"]
    winner = a if a["seatsAvailable"] > b["seatsAvailable"] else b
    missing = _has(result["answer"], str(a["seatsAvailable"]), str(b["seatsAvailable"]), a["instructor"]["name"], b["instructor"]["name"])
    if missing:
        return Check(False, "the answer gives both seat counts and both instructors", f"answer is missing {missing}")
    if winner["courseTitle"].lower() not in result["answer"].lower() and winner["courseCode"].lower() not in result["answer"].lower():
        return Check(False, "the answer names the course with more seats", f"{winner['courseTitle']} ({winner['seatsAvailable']} seats) is not named")
    return Check(True)


def unsupported_claims(result: dict) -> list[str]:
    """Facts in the final answer (course codes, instructor names, seat counts) that appear in NO tool observation."""
    evidence = " ".join(c["observation"] for c in result["tool_calls"]).lower()
    answer = result["answer"] or ""
    claims = [f"code {m}" for m in CODE_RE.findall(answer) if m.lower() not in evidence]
    claims += [f"instructor {m}" for m in INSTRUCTOR_RE.findall(answer) if m.lower() not in evidence]
    claims += [f"{m} seats" for m in SEATS_RE.findall(answer) if not re.search(rf"\b{m}\b", evidence)]
    return claims


@dataclass
class Case:
    id: str
    title: str
    prompt: str
    min_tool_calls: int
    required_tools: dict
    verifier: Callable[[dict], Check]


CASES = [
    Case("A", "search a term, then look up the first result",
         "Search the catalogue for courses about 'data', then look up the full details of the first search result and tell me its "
         "course code, title, instructor and description.", 2, {"search_courses": 1, "course_detail": 1}, verify_a),
    Case("B", "aggregate question plus one supporting example",
         "Which department has the most total seats across its courses? Back your answer with one example course from that department.",
         2, {"course_stats": 1}, verify_b),
    Case("C", "compare two courses (search plus two detail lookups)",
         "Compare 'Machine Learning Foundations' and 'Database Systems': which one has more available seats, and who teaches each? "
         "Look both courses up before answering.", 3, {"search_courses": 1, "course_detail": 2}, verify_c),
]
CASES_BY_ID = {c.id: c for c in CASES}


def oracle_correct(case_id: str, answer: str, repo=None) -> bool:
    """Answer-only ground truth read straight from the database (ignores HOW the agent got there).
    A verifier that rejects an answer this oracle accepts has made a false rejection."""
    import domain_tools

    repo = repo or domain_tools.default_repo()
    answer = answer or ""
    if case_id == "A":
        first = repo.search("data", 50)[0]
        detail = repo.get(first["id"])
        return not _has(answer, detail["courseCode"], detail["instructor"]["name"])
    if case_id == "B":
        top = max(repo.stats("department"), key=lambda g: g["totalSeats"])
        in_dept = [c for c in repo.search(top["group"], 50) if c["department"] == top["group"]]
        return not _has(answer, top["group"]) and any(c["courseCode"].lower() in answer.lower() or c["courseTitle"].lower() in answer.lower() for c in in_dept)
    if case_id == "C":
        ml = repo.get(repo.search("Machine Learning Foundations", 5)[0]["id"])
        db = repo.get(repo.search("Database Systems", 5)[0]["id"])
        winner = ml if ml["seatsAvailable"] > db["seatsAvailable"] else db
        return (not _has(answer, str(ml["seatsAvailable"]), str(db["seatsAvailable"]), ml["instructor"]["name"], db["instructor"]["name"])
                and (winner["courseTitle"].lower() in answer.lower() or winner["courseCode"].lower() in answer.lower()))
    raise ValueError(case_id)
