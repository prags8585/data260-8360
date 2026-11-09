import json
import re

from kafka_svc import config
from kafka_svc.catalogue import gather_facts

DEFAULT_PLAN = [
    "Identify which catalogue facts the question needs",
    "Look up those facts in the catalogue tools",
    "Answer in two or three sentences using only those facts",
]
_CODE = re.compile(r"\b[A-Z]{2,5}-\d{2,3}[A-Z]?\b")
_NUMBER = re.compile(r"\b\d{2,}\b")

PLANNER_SYSTEM = (
    "You are the Planner agent of a campus course-catalogue assistant. Write a short plan (2 to 4 steps, one sentence each) "
    'for answering the question from catalogue data. Reply with JSON only: {"plan": ["step 1", "step 2"]}'
)
WRITER_SYSTEM = (
    "You are the Writer agent of a campus course-catalogue assistant. Write a 2 to 4 sentence plain-text answer to the question "
    "using ONLY the facts JSON. Follow the plan. Copy numbers, course codes, department and instructor names exactly as given; "
    "do not invent any."
)


def plan_rule(question: str) -> list[str]:
    return list(DEFAULT_PLAN)


def plan_llm(model, question: str) -> tuple[list[str], str]:
    for _ in range(2):
        try:
            plan = json.loads(model.complete([("system", PLANNER_SYSTEM), ("user", question)]).content).get("plan")
        except (ValueError, AttributeError):
            continue
        if isinstance(plan, list) and 1 <= len(plan) <= 5 and all(isinstance(s, str) and s.strip() for s in plan):
            return [s.strip() for s in plan], "llm"
    return plan_rule(question), "fallback"


def top_department(facts: dict) -> dict:
    return max(facts["departments"], key=lambda g: g["totalSeats"])


def top_course_in(facts: dict, department: str) -> dict:
    return max((c for c in facts["courses"] if c["department"] == department), key=lambda c: c["seatsAvailable"])


def draft_rule(question: str, facts: dict) -> str:
    top = top_department(facts)
    course = top_course_in(facts, top["group"])
    return (f"{top['group']} has the most available seats ({top['totalSeats']} across {top['courses']} courses); "
            f"its largest course is {course['courseCode']} ({course['courseTitle']}) with {course['seatsAvailable']} seats.")


def draft_llm(model, question: str, plan: list[str], facts: dict) -> str:
    prompt = f"Question: {question}\nPlan: {json.dumps(plan)}\nFacts: {json.dumps(facts)}"
    return model.complete([("system", WRITER_SYSTEM), ("user", prompt)]).content.strip()


def write_draft(brain: str, model, question: str, plan: list[str]) -> tuple[str, dict]:
    facts = gather_facts(question)
    draft = draft_llm(model, question, plan, facts) if brain == "llm" else draft_rule(question, facts)
    return draft, facts


_MAX_WORDS = r"\b(most|largest|highest|biggest|greatest)\b"
_MIN_WORDS = r"\b(fewest|least|smallest|lowest)\b"


def expected_extreme(question: str, facts: dict) -> dict | None:
    """What a 'most / fewest seats' question should name: a department, a course, or (HW8's question) both.
    Returns None when the question does not ask for an extreme."""
    q = question.lower()
    if "seat" not in q:
        return None
    biggest = bool(re.search(_MAX_WORDS, q))
    if not biggest and not re.search(_MIN_WORDS, q):
        return None
    pick = max if biggest else min
    departments = facts["departments"]
    named = [g["group"] for g in departments if g["group"].lower() in q]
    wants_department = "department" in q and not named
    wants_course = "course" in q
    top_dept = pick(departments, key=lambda g: g["totalSeats"])
    if wants_department and wants_course:  # HW8: "which department ..., and which course there ..."
        course = pick((c for c in facts["courses"] if c["department"] == top_dept["group"]), key=lambda c: c["seatsAvailable"])
        return {"names": [top_dept["group"], course["courseCode"]],
                "detail": f"{top_dept['group']} ({top_dept['totalSeats']} seats) and {course['courseCode']} ({course['seatsAvailable']} seats)"}
    if wants_department:
        return {"names": [top_dept["group"]], "detail": f"{top_dept['group']} ({top_dept['totalSeats']} seats)"}
    if wants_course:
        pool = [c for c in facts["courses"] if not named or c["department"] in named]
        course = pick(pool, key=lambda c: c["seatsAvailable"])
        return {"names": [course["courseCode"]], "detail": f"{course['courseCode']} ({course['seatsAvailable']} seats)"}
    return None


def review_draft(question: str, draft: str, facts: dict) -> dict:
    allowed_numbers = {int(n) for n in _NUMBER.findall(json.dumps(facts))}
    names = [g["group"] for g in facts["departments"] + facts["instructors"]] + facts["course_codes"]
    extreme = expected_extreme(question, facts)
    checks = [
        ("length", 20 <= len(draft) <= 800, f"{len(draft)} characters"),
        ("numbers_grounded", all(int(n) in allowed_numbers for n in _NUMBER.findall(draft)),
         f"numbers in draft {sorted({int(n) for n in _NUMBER.findall(draft)})}"),
        ("codes_known", all(c in facts["course_codes"] for c in _CODE.findall(draft)),
         f"codes in draft {sorted(set(_CODE.findall(draft)))}"),
        ("uses_catalogue", any(n.lower() in draft.lower() for n in names), "names a department, instructor or course code"),
    ]
    if extreme:
        checks.append(("superlative_correct", all(n.lower() in draft.lower() for n in extreme["names"]), f"expected {extreme['detail']}"))
    return {"approved": all(ok for _, ok, _ in checks), "checks": [{"check": n, "passed": ok, "detail": d} for n, ok, d in checks]}


def make_model(json_mode: bool = False):
    from src.model_client import ModelClient
    return ModelClient(config.MODEL, 0.0, num_predict=400, json_mode=json_mode, seed=config.SEED)
