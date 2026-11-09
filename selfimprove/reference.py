"""Ground truth for Part 4: the reference dataset, a resolver that works out which facts a question needs, and an answer checker.

The question files hold only questions. Which facts a question needs, and what a correct answer must contain, is worked out
here from the reference dataset alone, so the Evaluator Agent never sees an 'expected answer' stored with a question."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_FILE = ROOT / "part4/reference_data.json"

CODE_RE = re.compile(r"\b[A-Za-z]{2,5}-\d{2,3}[A-Za-z]?\b")
NUMBER_RE = re.compile(r"(?<![\w.-])\d+(?![\w-])")
NUMBER_WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
UNAVAILABLE_RE = re.compile(r"\b(schedule|time|times|meet|meets|meeting|day|days|room|rooms|location|building|tuition|cost|costs|fee|fees|"
                            r"price|prerequisite|prerequisites|syllabus|textbook|credit|credits|unit|units|grade|grades|grading|exam|exams|"
                            r"waitlist|enrolled|enrolment|enrollment)\b")
CATALOGUE_WORDS_RE = re.compile(r"\b(seat|seats|course|courses|class|classes|instructor|instructors|teach|teaches|taught|professor|department|departments)\b")
DECLINE_RE = re.compile(r"(do(?:es)? not (?:have|include|contain|list|provide|cover|specify|mention|state)|don't have|doesn't (?:have|include|contain|list)|"
                        r"cannot|can't|can not|unable|not available|no information|no such|not (?:listed|found|in the catalogue|part of)|"
                        r"(?:is|are) not (?:provided|specified|included|mentioned|stated|given|recorded|offered)|isn't (?:listed|in|provided|included)|there is no|there are no|no course|only (?:answer|provide|have|cover)|outside|not (?:a )?(?:valid )?course)", re.I)
OPINION_RE = re.compile(r"\b(best|worst|easy|easiest|hard|hardest|difficult|recommend|recommendation|suggest|worth|should i|good|favou?rite|popular|enjoy|fun|boring)\b")
ALL_RE = re.compile(r"\b(total|altogether|together|combined|across all|in all|whole catalogue|entire catalogue|all (?:the )?courses|every course)\b")
MAX_RE = re.compile(r"\b(most|largest|highest|biggest|greatest)\b")
MIN_RE = re.compile(r"\b(fewest|least|smallest|lowest)\b")

FAILURE_TYPES = ("unsupported_answer", "wrong_decline", "missing_value", "wrong_value", "incomplete_list")


def load_reference(path: Path = REFERENCE_FILE) -> dict:
    return json.loads(Path(path).read_text())


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]


def strip_codes(text: str) -> str:
    return CODE_RE.sub(" ", text)


def numbers_in(text: str) -> set[int]:
    return {int(n) for n in NUMBER_RE.findall(strip_codes(text))}


def contains_number(text: str, value: int) -> bool:
    word = NUMBER_WORDS.get(value)
    return value in numbers_in(text) or bool(word and re.search(rf"\b{word}\b", text, re.I))


class Reference:
    def __init__(self, data: dict | None = None):
        self.data = data or load_reference()
        self.courses = self.data["courses"]
        self.by_code = {c["courseCode"].upper(): c for c in self.courses}
        self.departments = sorted({c["department"] for c in self.courses})
        self.instructors = [i["name"] for i in self.data["instructors"]]

    # ---- what does the question need? ---------------------------------------------------------------------------
    def resolve(self, question: str) -> dict:
        q = question.lower()
        codes = [c.upper() for c in CODE_RE.findall(question)]
        unknown = [c for c in codes if c not in self.by_code]
        courses = [self.by_code[c] for c in codes if c in self.by_code]
        for course in self.courses:  # courses named by title; the title is blanked out so 'Engineering Analytics' is not also a department
            if course["courseTitle"].lower() in q and course not in courses:
                courses.append(course)
                q = q.replace(course["courseTitle"].lower(), " ")
        instructors = [n for n in self.instructors if n.lower().removeprefix("dr. ") in q]
        departments = [d for d in self.departments if d.lower() in q]

        if unknown and not courses:
            return {"kind": "unknown_entity", "answerable": False, "detail": f"{', '.join(unknown)} is not in the catalogue"}
        if OPINION_RE.search(q):
            return {"kind": "opinion", "answerable": False, "detail": "the catalogue holds facts, not opinions, advice or recommendations"}
        if UNAVAILABLE_RE.search(q) and (courses or instructors or departments):
            return {"kind": "unavailable_field", "answerable": False, "detail": "the catalogue does not hold that kind of information"}
        if not (courses or instructors or departments) and not CATALOGUE_WORDS_RE.search(q):
            return {"kind": "unrelated", "answerable": False, "detail": "the question is not about the course catalogue"}

        if re.search(r"how many (courses|classes)|number of (courses|classes)", q):
            pool = self._courses_of(instructors, departments)
            return self._count("instructor_course_count" if instructors else "dept_course_count", pool)
        if instructors and re.search(r"\b(list|which courses|what courses|courses taught|classes taught)\b", q) and "seats" not in q:
            return self._listing("instructor_courses", self._courses_of(instructors, []))
        if departments and re.search(r"\b(list|which courses|what courses)\b", q):
            return self._listing("dept_courses", self._courses_of([], departments))
        if "total" in q and "seats" in q and (instructors or departments):
            pool = self._courses_of(instructors, departments)
            return {"kind": "instructor_total_seats" if instructors else "dept_total_seats", "answerable": True, "values": [sum(c["seatsAvailable"] for c in pool)],
                    "components": [c["seatsAvailable"] for c in pool], "codes": [c["courseCode"] for c in pool]}
        if "seat" in q and not (courses or instructors or departments) and ALL_RE.search(q):
            return {"kind": "all_total_seats", "answerable": True, "values": [sum(c["seatsAvailable"] for c in self.courses)],
                    "components": [c["seatsAvailable"] for c in self.courses], "codes": [c["courseCode"] for c in self.courses]}
        extreme = MAX_RE.search(q) or MIN_RE.search(q)
        if extreme and "seat" in q:
            pick = max if MAX_RE.search(q) else min
            if "department" in q and not departments:
                totals = {d: sum(c["seatsAvailable"] for c in self.courses if c["department"] == d) for d in self.departments}
                winner = pick(totals, key=totals.get)
                return {"kind": "department_extreme", "answerable": True, "names": [winner], "values": [totals[winner]], "candidates": list(totals),
                        "components": list(totals.values())}
            pool = self._courses_of([], departments) if departments else self.courses
            winner = pick(pool, key=lambda c: c["seatsAvailable"])
            return {"kind": "course_extreme", "answerable": True, "names": [winner["courseCode"]], "values": [winner["seatsAvailable"]],
                    "candidates": [c["courseCode"] for c in pool], "components": [c["seatsAvailable"] for c in pool]}
        if courses:
            c = courses[0]
            if re.search(r"\b(who|instructor|teach|teaches|taught|professor)\b", q):
                return {"kind": "instructor_of", "answerable": True, "names": [c["instructor"]], "codes": [c["courseCode"]]}
            if re.search(r"\b(title|name|called)\b", q):
                return {"kind": "title_of", "answerable": True, "names": [c["courseTitle"]], "codes": [c["courseCode"]]}
            if "department" in q:
                return {"kind": "department_of", "answerable": True, "names": [c["department"]], "codes": [c["courseCode"]]}
            if "seat" in q:
                return {"kind": "seats_of", "answerable": True, "values": [c["seatsAvailable"]], "codes": [c["courseCode"]]}
        return {"kind": "unresolved", "answerable": False, "detail": "the question could not be matched to a reference fact"}

    def _courses_of(self, instructors: list[str], departments: list[str]) -> list[dict]:
        return [c for c in self.courses if (not instructors or c["instructor"] in instructors) and (not departments or c["department"] in departments)]

    @staticmethod
    def _count(kind: str, pool: list[dict]) -> dict:
        return {"kind": kind, "answerable": True, "values": [len(pool)], "components": [c["seatsAvailable"] for c in pool],
                "codes": [c["courseCode"] for c in pool]}

    @staticmethod
    def _listing(kind: str, pool: list[dict]) -> dict:
        return {"kind": kind, "answerable": True, "listed": [c["courseCode"] for c in pool], "codes": [c["courseCode"] for c in pool]}

    # ---- is the answer right? -----------------------------------------------------------------------------------
    def check(self, question: str, answer: str) -> dict:
        """{'passed', 'failure_type', 'explanation', 'feedback', 'kind', 'facts'} - feedback is what the Evaluator tells the Answering Agent."""
        spec = self.resolve(question)
        answer = (answer or "").strip()
        declined = bool(DECLINE_RE.search(first_sentence(answer)))
        if not spec["answerable"]:
            if declined:
                return self._result(spec, True, None, "the answer correctly says the catalogue cannot answer this", "")
            return self._result(spec, False, "unsupported_answer",
                                f"the answer gives details although {spec['detail']}",
                                "The reference catalogue only holds course code, title, department, seats available and instructor. It has nothing that "
                                f"answers this question ({spec['detail']}). Say that the catalogue cannot answer it; do not guess or use general knowledge.")
        facts = self._facts_text(spec)
        if declined and not (spec["kind"] in ("instructor_course_count", "dept_course_count") and re.search(r"\bno\b|\bzero\b", answer, re.I)):
            return self._result(spec, False, "wrong_decline", "the answer refuses a question the catalogue can answer",
                                f"This question can be answered from the catalogue. Reference facts: {facts}.", facts)

        missing = self._missing(spec, answer)
        wrong = self._wrong(spec, answer)
        if not missing and not wrong:
            return self._result(spec, True, None, f"the answer matches the reference ({facts})", "", facts)
        if wrong:
            kind = "incomplete_list" if spec["kind"].endswith("courses") and missing and not wrong else "wrong_value"
            return self._result(spec, False, kind, f"the answer contains {wrong[0]} that the reference does not support",
                                f"The answer states {wrong[0]}, which does not match the reference. Reference facts: {facts}. Correct the answer.", facts)
        kind = "incomplete_list" if spec["kind"].endswith("courses") else "missing_value"
        return self._result(spec, False, kind, f"the answer omits {', '.join(missing)}",
                            f"The answer does not state {', '.join(missing)}. Reference facts: {facts}. State the requested value explicitly.", facts)

    def _missing(self, spec: dict, answer: str) -> list[str]:
        missing = []
        for value in spec.get("values", []):
            if not contains_number(answer, value):
                missing.append(f"the value {value}")
        for name in spec.get("names", []):
            if name.lower() not in answer.lower():
                missing.append(name)
        for code in spec.get("listed", []):
            if code.lower() not in answer.lower():
                missing.append(code)
        return missing

    def _wrong(self, spec: dict, answer: str) -> list[str]:
        wrong = []
        if "values" in spec:
            allowed = set(spec["values"]) | set(spec.get("components", []))
            stray = sorted(numbers_in(answer) - allowed)
            if stray:
                wrong.append(f"the number {stray[0]}")
        if "listed" in spec:
            extra = [c.upper() for c in CODE_RE.findall(answer) if c.upper() in self.by_code and c.upper() not in spec["listed"]]
            if extra:
                wrong.append(f"the course {extra[0]}")
        others = {"instructor_of": self.instructors, "department_of": self.departments, "title_of": [c["courseTitle"] for c in self.courses]}
        for other in others.get(spec["kind"], []):
            if other not in spec.get("names", []) and other.lower() in answer.lower():
                wrong.append(other)
        if spec["kind"] in ("course_extreme", "department_extreme"):
            order = sorted((answer.lower().find(c.lower()), c) for c in spec["candidates"] if c.lower() in answer.lower())
            if order and order[0][1] != spec["names"][0]:
                wrong.append(order[0][1])
        return wrong

    def _facts_text(self, spec: dict) -> str:
        parts = []
        if "values" in spec:
            parts.append("value " + ", ".join(str(v) for v in spec["values"]))
        if "names" in spec:
            parts.append(", ".join(spec["names"]))
        if "listed" in spec:
            parts.append("courses " + ", ".join(spec["listed"]))
        if spec.get("components") and len(spec["components"]) > 1:
            parts.append("from seat counts " + " + ".join(str(v) for v in spec["components"]))
        return "; ".join(parts) or "see the catalogue"

    @staticmethod
    def _result(spec: dict, passed: bool, failure_type: str | None, explanation: str, feedback: str, facts: str = "") -> dict:
        return {"passed": passed, "failure_type": failure_type, "explanation": explanation, "feedback": feedback, "kind": spec["kind"], "facts": facts}
