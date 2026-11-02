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


def review_draft(question: str, draft: str, facts: dict) -> dict:
    allowed_numbers = {int(n) for n in _NUMBER.findall(json.dumps(facts))}
    names = [g["group"] for g in facts["departments"] + facts["instructors"]] + facts["course_codes"]
    asks_most = bool(re.search(r"\bmost\b.*\bseats\b|\bseats\b.*\bmost\b", question.lower()))
    expected = top_department(facts)
    expected_course = top_course_in(facts, expected["group"])
    checks = [
        ("length", 20 <= len(draft) <= 800, f"{len(draft)} characters"),
        ("numbers_grounded", all(int(n) in allowed_numbers for n in _NUMBER.findall(draft)),
         f"numbers in draft {sorted({int(n) for n in _NUMBER.findall(draft)})}"),
        ("codes_known", all(c in facts["course_codes"] for c in _CODE.findall(draft)),
         f"codes in draft {sorted(set(_CODE.findall(draft)))}"),
        ("uses_catalogue", any(n.lower() in draft.lower() for n in names), "names a department, instructor or course code"),
    ]
    if asks_most:
        wants_course = "course" in question.lower()
        correct = expected["group"].lower() in draft.lower() and (not wants_course or expected_course["courseCode"] in draft)
        checks.append(("superlative_correct", correct,
                       f"expected {expected['group']} ({expected['totalSeats']} seats)"
                       + (f" and {expected_course['courseCode']} ({expected_course['seatsAvailable']} seats)" if wants_course else "")))
    return {"approved": all(ok for _, ok, _ in checks), "checks": [{"check": n, "passed": ok, "detail": d} for n, ok, d in checks]}


def make_model(json_mode: bool = False):
    from src.model_client import ModelClient
    return ModelClient(config.MODEL, 0.0, num_predict=400, json_mode=json_mode, seed=config.SEED)
