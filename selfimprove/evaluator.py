from selfimprove.reference import Reference


class EvaluatorAgent:
    """Checks an answer against the reference dataset and returns PASS or REVISE with an explanation and feedback.

    The message it sends back to the Answering Agent is a plain dict:
      {"result": "PASS" | "REVISE", "explanation": str, "feedback": str, "failure_type": str | None, "attempt": int}"""

    def __init__(self, reference: Reference | None = None):
        self.reference = reference or Reference()

    def evaluate(self, question: str, answer: str, attempt: int = 1) -> dict:
        checked = self.reference.check(question, answer)
        return {"result": "PASS" if checked["passed"] else "REVISE", "explanation": checked["explanation"], "feedback": checked["feedback"],
                "failure_type": checked["failure_type"], "kind": checked["kind"], "attempt": attempt}
