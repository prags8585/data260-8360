import json
import os
from datetime import date
from pathlib import Path

import numpy as np

LESSON_TEMPLATES = {
    "unsupported_answer": (
        "The answer gives details the course catalogue does not contain: a question that is not about courses, a course that is not listed, "
        "or a field the catalogue does not hold such as schedules, rooms, tuition or prerequisites.",
        "Answer only from the catalogue table. It holds just course code, title, department, seats and instructor. If the question is not "
        "about those, or names a course that is not listed, say clearly that the catalogue cannot answer it; do not guess or use general knowledge."),
    "unsupported_answer:opinion": (
        "The answer gives an opinion, a recommendation or a judgement (best, easy, difficult, worth taking) although the catalogue holds only facts.",
        "The catalogue holds facts only: course code, title, department, seats and instructor. When a question asks for an opinion, a recommendation, "
        "how hard a course is or who is the best, begin with a sentence saying that the catalogue cannot judge or recommend; do not give an opinion."),
    "wrong_value:all_total_seats": (
        "The answer gives a wrong total for the seats of all courses in the catalogue.",
        "For a total over the whole catalogue, write down the seats of every row of the table one by one, add them up in order and state the sum."),
    "wrong_decline": (
        "The answer refuses a question that the catalogue can answer.",
        "If the course, instructor or department is in the catalogue table, answer from its rows; decline only when the information is really missing."),
    "missing_value": (
        "The answer leaves out the value the question asks for.",
        "State the requested value (the number, name or title) explicitly in the first sentence."),
    "wrong_value": (
        "The answer gives a wrong total, count, name or highest/lowest value.",
        "For totals, counts and most/fewest questions, first list the relevant catalogue rows with their seat numbers, then compute the result from that list."),
    "incomplete_list": (
        "The answer lists only some of the courses the question asks for.",
        "When asked to list courses, go through every row of the catalogue and name every course that matches."),
}


class LessonStore:
    """lessons.json: lesson_id, failure_pattern, correction, created_at, use_count."""

    def __init__(self, path: str | Path, min_similarity: float = 0.2, top_k: int = 3):
        self.path = Path(path)
        self.min_similarity, self.top_k = min_similarity, top_k
        self.lessons: list[dict] = json.loads(self.path.read_text()) if self.path.exists() else []
        self._vectors: dict[str, np.ndarray] = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.lessons, indent=2) + "\n")

    def has_pattern(self, failure_pattern: str) -> bool:
        return any(lesson["failure_pattern"] == failure_pattern for lesson in self.lessons)

    def add(self, failure_pattern: str, correction: str) -> dict | None:
        if self.has_pattern(failure_pattern):
            return None
        lesson = {"lesson_id": f"lesson_{len(self.lessons) + 1:03d}", "failure_pattern": failure_pattern, "correction": correction,
                  "created_at": date.today().isoformat(), "use_count": 0}
        self.lessons.append(lesson)
        return lesson

    def add_from_failure(self, failure_type: str, example_question: str, kind: str | None = None) -> dict | None:
        """failure_type picks the template; a more specific template 'failure_type:kind' is used when one exists."""
        pattern, correction = LESSON_TEMPLATES.get(f"{failure_type}:{kind}", LESSON_TEMPLATES[failure_type])
        return self.add(f"{pattern} Example question: {example_question}", correction) if not any(
            pattern in lesson["failure_pattern"] for lesson in self.lessons) else None

    def remove(self, lesson_id: str) -> None:
        self.lessons = [lesson for lesson in self.lessons if lesson["lesson_id"] != lesson_id]

    def relevant(self, question: str) -> list[dict]:
        """Lessons whose failure_pattern is semantically close to the question (cosine similarity, top_k)."""
        if not self.lessons:
            return []
        scored = sorted(((self._similarity(question, lesson), lesson) for lesson in self.lessons), key=lambda pair: -pair[0])
        return [lesson for score, lesson in scored[: self.top_k] if score >= self.min_similarity]

    def mark_used(self, lesson_ids: list[str]) -> None:
        for lesson in self.lessons:
            if lesson["lesson_id"] in lesson_ids:
                lesson["use_count"] += 1

    def _similarity(self, question: str, lesson: dict) -> float:
        from cache_svc.embedding import embed
        key = lesson["failure_pattern"]
        if key not in self._vectors:
            self._vectors[key] = embed([key])[0]
        return float(np.dot(embed([question])[0], self._vectors[key]))


def lesson_path(name: str) -> Path:
    return Path(os.environ.get("HW9_PART4_DIR", Path(__file__).resolve().parent.parent / "part4")) / name
