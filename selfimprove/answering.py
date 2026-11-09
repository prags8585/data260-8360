import time
from typing import Callable

from selfimprove.lessons import LessonStore

SYSTEM = (
    "You are the assistant of a university's course catalogue. Use the catalogue below to answer the user's question. "
    "Answer in one or two short sentences.\n\n"
    "Catalogue (course code | title | department | seats available | instructor):\n{catalogue}"
)


def catalogue_text(rows: list[dict]) -> str:
    return "\n".join(f"{r['courseCode']} | {r['courseTitle']} | {r['department']} | {r['seatsAvailable']} | {r['instructorName']}" for r in rows)


class AnsweringAgent:
    """Generates an answer to a question from the live course catalogue. Lessons from earlier mistakes (when enabled) are put in
    the system prompt; when the Evaluator asked for a revision, the previous answer and its feedback are put in the user message."""

    def __init__(self, model, catalogue: Callable[[], list[dict]], lessons: LessonStore | None = None):
        self.model, self.catalogue, self.lessons = model, catalogue, lessons

    def answer(self, question: str, attempt: int = 1, previous: str | None = None, feedback: str | None = None,
               forced: str | None = None) -> dict:
        """`forced` replaces the model's first attempt with a given answer (used for the controlled test case)."""
        t0 = time.perf_counter()
        used = self.lessons.relevant(question) if self.lessons is not None else []
        if forced is not None and attempt == 1:
            text = forced
        else:
            system = SYSTEM.format(catalogue=catalogue_text(self.catalogue()))
            if used:
                system += "\n\nLessons from earlier mistakes (follow them):\n" + "\n".join(f"- {lesson['correction']}" for lesson in used)
            user = question
            if previous is not None and feedback:
                user += f"\n\nYour previous answer was: {previous}\nThe evaluator says: {feedback}\nWrite a corrected answer."
            text = self.model.complete([("system", system), ("user", user)]).content.strip()
        if used and self.lessons is not None:
            self.lessons.mark_used([lesson["lesson_id"] for lesson in used])
        return {"answer": text, "attempt": attempt, "lessons_used": [lesson["lesson_id"] for lesson in used],
                "latency_s": round(time.perf_counter() - t0, 2)}
