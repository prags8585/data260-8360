import json
import logging
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cache_svc import config as cache_config
from cache_svc.cost_model import COST_FALSE_HIT, COST_HIT, COST_MISS, total_cost
from cache_svc.course_db import CourseDB
from cache_svc.ingress import QAIngress, deps_of
from cache_svc.semantic_cache import to_bytes
from db import Base
from kafka_svc import brains
from models import Course, Instructor
from selfimprove.answering import AnsweringAgent, catalogue_text
from selfimprove.evaluator import EvaluatorAgent
from selfimprove.lessons import LessonStore
from selfimprove.pipeline import run_question, summarize, validation_decision
from selfimprove.reference import Reference

ROOT = Path(__file__).resolve().parent


# --- fakes: SQLite instead of MySQL, a dict instead of Redis ------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self.data: dict[str, int] = {}

    def incr(self, key):
        self.data[key] = self.data.get(key, 0) + 1
        return self.data[key]

    def incrby(self, key, amount):
        self.data[key] = self.data.get(key, 0) + amount
        return self.data[key]

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)

    def get(self, key):
        return self.data.get(key)


def make_db() -> CourseDB:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as session:
        session.add_all([Instructor(id=1, name="Dr. Priya Nair", department="Data Science", email="p@x.edu"),
                         Instructor(id=2, name="Dr. Marcus Lee", department="Computer Science", email="m@x.edu")])
        session.add_all([Course(id=1, course_title="Intro", course_code="DATA-260", department="Data Science", seats_available=40, instructor_id=1),
                         Course(id=2, course_title="Databases", course_code="CS-157A", department="Computer Science", seats_available=45, instructor_id=2)])
        session.commit()
    return CourseDB(session_factory=factory, redis_client=FakeRedis())


def db_views(db: CourseDB, course_id: int) -> int:
    with db.session_factory() as session:
        return session.execute(select(Course.views).where(Course.id == course_id)).scalar_one()


class FakeCache:
    """Same interface as SemanticCache for the parts QAIngress uses; similarity is whatever the test sets."""

    def __init__(self):
        self.entries: dict[str, dict] = {}
        self.similarity = 0.0
        self.stats: list[tuple[str, float]] = []

        class Client:
            def hincrby(_self, *args):  # noqa: N805
                self.stats.append(("stale", 0))
        self.client = Client()

    def lookup(self, vector):
        if not self.entries:
            return None
        key, entry = next(iter(self.entries.items()))
        return {"key": key, **entry, "similarity": self.similarity}

    def store(self, question, vector, answer, data_version, deps):
        key = f"k{len(self.entries) + 1}"
        self.entries[key] = {"query": question, "answer": answer, "data_version": data_version, "deps": deps}
        return key

    def delete(self, key):
        self.entries.pop(key, None)

    def record(self, outcome, latency_ms):
        self.stats.append((outcome, latency_ms))


def make_ingress(threshold=0.85, agent_status="approved"):
    import cache_svc.ingress as ingress_module
    ingress_module.embed = lambda texts: [np.zeros(4, dtype=np.float32) for _ in texts]
    calls = []

    def agent(question):
        calls.append(question)
        return {"status": agent_status, "answer": "agent answer", "correlation_id": "c"}

    db, cache = make_db(), FakeCache()
    return QAIngress(cache, db, agent, threshold=threshold), cache, db, calls


# --- Part 1: Redis view counter ----------------------------------------------------------------------------------

def test_configuration_follows_the_personal_values():
    assert cache_config.PREFIX == "s8360" and cache_config.PORT_BASE == 8260
    assert cache_config.views_key(7) == "s8360:views:course:7"
    assert cache_config.ENTRY_PREFIX.startswith("s8360:") and cache_config.INDEX_NAME.startswith("s8360_")
    assert cache_config.DEFAULT_THRESHOLD == 0.85


def test_counter_returns_the_running_total_and_syncs_every_ten():
    db = make_db()
    totals = [db.increment_course_views(1) for _ in range(25)]
    assert totals == list(range(1, 26))
    assert db_views(db, 1) == 20  # last sync at 20; 21-25 live only in Redis
    assert db.redis_client.get("s8360:views:course:1") == 25
    assert db_views(db, 2) == 0


def test_counter_resumes_from_the_synced_value_when_the_redis_key_is_lost():
    db = make_db()
    for _ in range(20):
        db.increment_course_views(1)
    db.redis_client.delete("s8360:views:course:1")
    assert db.increment_course_views(1) == 21


def test_counter_logs_the_sync_message():
    db = make_db()
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    log = logging.getLogger("course_db")
    log.addHandler(handler)
    log.disabled = False
    log.setLevel(logging.INFO)
    logging.disable(logging.NOTSET)  # main() silences logging for the whole run
    try:
        for _ in range(10):
            db.increment_course_views(1)
    finally:
        log.removeHandler(handler)
        logging.disable(logging.CRITICAL)
    assert any(m.startswith("Synced views to database") for m in records)


# --- Part 2/3: semantic cache logic ------------------------------------------------------------------------------

def test_vectors_are_stored_as_float32_bytes():
    assert len(to_bytes(np.ones(384))) == 384 * 4


def test_deps_of_finds_course_codes():
    assert deps_of("How many seats in DATA-260 and CS-157A?") == ["CS-157A", "DATA-260"]
    assert deps_of("Which department has the most seats?") == []


def test_data_version_changes_with_seats_but_not_with_views():
    db = make_db()
    before = db.data_version(["DATA-260"])
    db.increment_course_views(1)
    for _ in range(9):
        db.increment_course_views(1)  # the 10th sync rewrites the views column
    assert db.data_version(["DATA-260"]) == before
    db.set_seats("DATA-260", 12)
    assert db.data_version(["DATA-260"]) != before
    assert db.data_version(["CS-157A"]) == make_db().data_version(["CS-157A"])  # another course is unaffected
    assert db.data_version() != make_db().data_version()  # the all-courses fingerprint sees the change


def test_miss_runs_the_agent_and_stores_the_answer():
    ingress, cache, db, calls = make_ingress()
    result = ingress.ask("How many seats in DATA-260?")
    assert result["is_cached"] is False and calls == ["How many seats in DATA-260?"] and len(cache.entries) == 1
    stored = next(iter(cache.entries.values()))
    assert stored["deps"] == "DATA-260" and stored["data_version"] == db.data_version(["DATA-260"])


def test_hit_above_the_threshold_skips_the_agent_and_reports_the_similarity():
    ingress, cache, _, calls = make_ingress(threshold=0.85)
    ingress.ask("How many seats in DATA-260?")
    cache.similarity = 0.9
    result = ingress.ask("What is the seat availability of DATA-260?")
    assert result["is_cached"] is True and result["similarity"] == 0.9 and result["answer"] == "agent answer"
    assert len(calls) == 1 and "latency_ms" in result


def test_similarity_exactly_at_the_threshold_is_a_hit_and_just_below_is_a_miss():
    ingress, cache, _, calls = make_ingress(threshold=0.85)
    ingress.ask("How many seats in DATA-260?")
    cache.similarity = 0.85
    assert ingress.ask("q2")["is_cached"] is True
    cache.similarity = 0.8499
    assert ingress.ask("q3")["is_cached"] is False and len(calls) == 2


def test_threshold_can_be_overridden_per_request():
    ingress, cache, _, _ = make_ingress(threshold=0.85)
    ingress.ask("How many seats in DATA-260?")
    cache.similarity = 0.8
    assert ingress.ask("q2")["is_cached"] is False
    assert ingress.ask("q2", threshold=0.75)["is_cached"] is True


def test_rejected_agent_answers_are_not_cached():
    ingress, cache, _, _ = make_ingress(agent_status="rejected")
    result = ingress.ask("What is the capital of France?")
    assert result["is_cached"] is False and result["status"] == "rejected" and cache.entries == {}


def test_store_false_keeps_the_cache_read_only():
    ingress, cache, _, _ = make_ingress()
    ingress.ask("How many seats in DATA-260?", store=False)
    assert cache.entries == {}


def test_stale_answer_is_served_without_validation_and_invalidated_with_it():
    ingress, cache, db, calls = make_ingress()
    ingress.ask("How many seats are available in DATA-260?")
    cache.similarity = 1.0
    db.set_seats("DATA-260", 12)
    stale = ingress.ask("How many seats are available in DATA-260?", validate_version=False)
    assert stale["is_cached"] is True and len(calls) == 1  # the old answer, although the row changed
    fresh = ingress.ask("How many seats are available in DATA-260?", validate_version=True)
    assert fresh["is_cached"] is False and fresh["stale_invalidated"] is True and len(calls) == 2
    assert next(iter(cache.entries.values()))["data_version"] == db.data_version(["DATA-260"])


def test_changing_another_course_does_not_invalidate_the_answer():
    ingress, cache, db, calls = make_ingress()
    ingress.ask("How many seats are available in DATA-260?")
    cache.similarity = 1.0
    db.set_seats("CS-157A", 1)
    assert ingress.ask("How many seats are available in DATA-260?")["is_cached"] is True and len(calls) == 1


def test_cost_model_prices_a_false_hit_far_above_a_miss():
    assert total_cost(hits=10, misses=5, false_hits=1) == round(10 * COST_HIT + 5 * COST_MISS + COST_FALSE_HIT, 4)
    assert COST_FALSE_HIT > 10 * COST_MISS > COST_HIT


def test_cache_cases_file_has_the_required_40_labeled_cases():
    spec = yaml.safe_load((ROOT / "cache_cases.yaml").read_text())
    cases = spec["cases"]
    assert len(cases) == 40 and len({c["id"] for c in cases}) == 40
    for category in ("exact_duplicate", "paraphrase", "superficially_similar", "unrelated"):
        assert sum(c["category"] == category for c in cases) == 10
    seeds = {s["id"]: s["query"] for s in spec["seed_queries"]}
    for c in cases:
        assert c["expected_hit"] == (c["category"] in ("exact_duplicate", "paraphrase"))
        if c["category"] == "exact_duplicate":
            assert c["query"] == seeds[c["cached_seed"]]
        if c["category"] == "paraphrase":
            assert c["query"] != seeds[c["cached_seed"]]


# --- HW8 Reviewer fix --------------------------------------------------------------------------------------------

FACTS = {"departments": [{"group": "Computer Science", "courses": 2, "totalSeats": 95}, {"group": "Data Science", "courses": 3, "totalSeats": 105},
                         {"group": "Engineering", "courses": 1, "totalSeats": 25}],
         "instructors": [], "course_codes": ["DATA-260", "CS-146", "ENGR-200"],
         "courses": [{"courseCode": "DATA-260", "department": "Data Science", "seatsAvailable": 40},
                     {"courseCode": "CS-146", "department": "Computer Science", "seatsAvailable": 50},
                     {"courseCode": "ENGR-200", "department": "Engineering", "seatsAvailable": 25}]}


def test_reviewer_accepts_the_course_with_most_seats_overall_not_only_inside_the_top_department():
    q = "Which course has the most available seats?"
    assert brains.expected_extreme(q, FACTS)["names"] == ["CS-146"]
    assert brains.review_draft(q, "CS-146 has the most seats: 50.", FACTS)["approved"]
    assert not brains.review_draft(q, "DATA-260 has the most seats: 40.", FACTS)["approved"]


def test_reviewer_handles_fewest_department_and_the_original_hw8_question():
    assert brains.expected_extreme("Which department has the fewest available seats?", FACTS)["names"] == ["Engineering"]
    assert brains.expected_extreme("Which Data Science course has the most seats?", FACTS)["names"] == ["DATA-260"]
    both = brains.expected_extreme("Which department has the most available seats, and which course there has the most seats?", FACTS)
    assert both["names"] == ["Data Science", "DATA-260"]
    assert brains.expected_extreme("How many seats are available in DATA-260?", FACTS) is None


# --- Part 4: reference, evaluator, lessons, pipeline ---------------------------------------------------------------

GOLD_KINDS = {
    "tr01": "seats_of",
    "tr02": "instructor_of",
    "tr03": "dept_total_seats",
    "tr04": "course_extreme",
    "tr05": "instructor_course_count",
    "tr06": "unrelated",
    "tr07": "unavailable_field",
    "tr08": "unknown_entity",
    "tr09": "opinion",
    "tr10": "opinion",
    "tr11": "all_total_seats",
    "tr12": "opinion",
    "tr13": "unavailable_field",
    "tr14": "all_total_seats",
    "va01": "seats_of",
    "va02": "department_of",
    "va03": "opinion",
    "va04": "opinion",
    "va05": "all_total_seats",
    "va06": "instructor_courses",
    "va07": "unavailable_field",
    "va08": "opinion",
    "va09": "unknown_entity",
    "va10": "dept_total_seats",
    "va11": "opinion",
    "va12": "all_total_seats",
    "te01": "seats_of",
    "te02": "instructor_of",
    "te03": "dept_total_seats",
    "te04": "course_extreme",
    "te05": "instructor_course_count",
    "te06": "department_extreme",
    "te07": "dept_courses",
    "te08": "title_of",
    "te09": "unavailable_field",
    "te10": "opinion",
    "te11": "opinion",
    "te12": "opinion",
    "te13": "all_total_seats",
    "te14": "all_total_seats",
    "te15": "opinion",
    "te16": "unknown_entity",
    "te17": "unrelated",
    "te18": "course_extreme",
}


def test_every_question_in_the_input_files_resolves_to_the_intended_kind():
    ref = Reference()
    seen = {}
    for name in ("training_data", "validation_data", "test_data"):
        for item in json.loads((ROOT / f"part4/{name}.json").read_text()):
            assert set(item) == {"id", "question"}  # inputs only: no expected answers in the input files
            seen[item["id"]] = ref.resolve(item["question"])["kind"]
    assert seen == GOLD_KINDS


def test_question_sets_do_not_overlap():
    questions = {name: {i["question"] for i in json.loads((ROOT / f"part4/{name}.json").read_text())} for name in ("training_data", "validation_data", "test_data")}
    assert not (questions["training_data"] & questions["test_data"]) and not (questions["validation_data"] & questions["test_data"])
    assert not (questions["training_data"] & questions["validation_data"])


def test_reference_matches_the_course_rows_in_the_documented_snapshot():
    ref = Reference()
    assert len(ref.courses) == 6 and ref.by_code["DATA-260"]["seatsAvailable"] == 40 and ref.by_code["ENGR-200"]["instructor"] == "Dr. Samuel Okafor"


def verdict(question: str, answer: str) -> dict:
    return Reference().check(question, answer)


def test_evaluator_passes_correct_answers_and_names_the_failure_for_wrong_ones():
    q = "How many seats are available in DATA-245?"
    assert verdict(q, "DATA-245 has 35 seats available.")["passed"]
    wrong = verdict(q, "DATA-245 has 30 seats available.")
    assert not wrong["passed"] and wrong["failure_type"] == "wrong_value" and "35" in wrong["feedback"]
    missing = verdict(q, "DATA-245 still has seats available.")
    assert not missing["passed"] and missing["failure_type"] == "missing_value" and "35" in missing["feedback"]


def test_evaluator_requires_a_decline_for_questions_the_catalogue_cannot_answer():
    for q in ("What is the capital of France?", "What time does DATA-260 meet?", "How many seats are available in DATA-999?"):
        assert verdict(q, "The capital is Paris. The catalogue cannot help.")["failure_type"] == "unsupported_answer"
        assert verdict(q, "The catalogue does not have that information.")["passed"]


def test_evaluator_flags_a_refusal_of_an_answerable_question():
    result = verdict("Who teaches DATA-245?", "I cannot answer that from the catalogue.")
    assert result["failure_type"] == "wrong_decline"


def test_evaluator_checks_totals_counts_lists_and_extremes():
    assert verdict("What is the total number of seats in the Computer Science department?", "It has 95 seats (45 + 50).")["passed"]
    assert verdict("What is the total number of seats in the Computer Science department?", "It has 90 seats.")["failure_type"] == "wrong_value"
    assert verdict("How many courses does Dr. Marcus Lee teach?", "Dr. Marcus Lee teaches two courses: CS-157A and CS-146.")["passed"]
    assert verdict("List the courses taught by Dr. Marcus Lee.", "CS-157A and CS-146.")["passed"]
    assert verdict("List the courses taught by Dr. Marcus Lee.", "CS-157A.")["failure_type"] == "incomplete_list"
    assert verdict("List the courses taught by Dr. Marcus Lee.", "CS-157A, CS-146 and DATA-260.")["failure_type"] == "wrong_value"
    assert verdict("Which course has the most available seats?", "CS-146 has the most seats (50), more than DATA-260 (40).")["passed"]
    assert verdict("Which course has the most available seats?", "DATA-260 has 40 seats, CS-146 has 50.")["failure_type"] == "wrong_value"
    assert verdict("Which department has the fewest available seats?", "Engineering, with 25 seats.")["passed"]
    assert verdict("Who teaches DATA-245?", "Dr. Marcus Lee teaches DATA-245.")["failure_type"] == "wrong_value"


def test_evaluator_agent_message_has_result_explanation_and_feedback():
    message = EvaluatorAgent().evaluate("Who teaches DATA-245?", "Nobody knows.", attempt=1)
    assert message["result"] == "REVISE" and message["explanation"] and message["feedback"] and message["attempt"] == 1
    assert EvaluatorAgent().evaluate("Who teaches DATA-245?", "Dr. Elena Rossi.", attempt=2)["result"] == "PASS"


class ScriptedModel:
    """Returns the next scripted reply; remembers what it was asked."""

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def complete(self, messages):
        self.prompts.append(messages)
        return type("R", (), {"content": self.replies.pop(0)})()


ROWS = [{"courseCode": "DATA-245", "courseTitle": "ML", "department": "Data Science", "seatsAvailable": 35, "instructorName": "Dr. Elena Rossi"}]


def test_catalogue_text_lists_one_row_per_course():
    assert catalogue_text(ROWS) == "DATA-245 | ML | Data Science | 35 | Dr. Elena Rossi"


def test_revision_uses_the_feedback_and_stops_after_the_second_attempt():
    model = ScriptedModel(["It has some seats.", "It has 35 seats."])
    agent = AnsweringAgent(model, lambda: ROWS)
    result = run_question({"id": "x", "question": "How many seats are available in DATA-245?"}, agent, EvaluatorAgent(), repair=True)
    assert result["attempt_count"] == 2 and result["final_result"] == "PASS"
    assert "Your previous answer was: It has some seats." in model.prompts[1][1][1] and "35" in model.prompts[1][1][1]
    never_right = ScriptedModel(["a", "b", "c"])
    result = run_question({"id": "x", "question": "How many seats are available in DATA-245?"}, AnsweringAgent(never_right, lambda: ROWS), EvaluatorAgent(), repair=True)
    assert result["attempt_count"] == 2 and result["final_result"] == "REVISE" and len(never_right.replies) == 1  # a third attempt never happens


def test_without_repair_there_is_exactly_one_attempt_and_no_feedback():
    model = ScriptedModel(["It has some seats."])
    result = run_question({"id": "x", "question": "How many seats are available in DATA-245?"}, AnsweringAgent(model, lambda: ROWS), EvaluatorAgent(), repair=False)
    assert result["attempt_count"] == 1 and result["final_result"] == "REVISE" and len(model.prompts) == 1


def test_a_correct_first_answer_needs_no_revision():
    model = ScriptedModel(["DATA-245 has 35 seats."])
    result = run_question({"id": "x", "question": "How many seats are available in DATA-245?"}, AnsweringAgent(model, lambda: ROWS), EvaluatorAgent(), repair=True)
    assert result["attempt_count"] == 1 and result["final_result"] == "PASS"


def test_forced_first_answer_replaces_only_the_first_attempt():
    model = ScriptedModel(["DATA-245 has 35 seats."])
    result = run_question({"id": "x", "question": "How many seats are available in DATA-245?"}, AnsweringAgent(model, lambda: ROWS), EvaluatorAgent(),
                          repair=True, forced_first="Seats are available.")
    assert result["attempts"][0]["answer"] == "Seats are available." and result["attempt_count"] == 2 and result["final_result"] == "PASS"
    assert len(model.prompts) == 1  # the model was only asked for the revision


def test_lesson_store_creates_one_lesson_per_failure_pattern_with_the_required_fields():
    with tempfile.TemporaryDirectory() as tmp:
        store = LessonStore(Path(tmp) / "lessons.json")
        first = store.add_from_failure("unsupported_answer", "What is the capital of France?")
        assert set(first) == {"lesson_id", "failure_pattern", "correction", "created_at", "use_count"} and first["use_count"] == 0
        assert store.add_from_failure("unsupported_answer", "Who won the 2018 World Cup?") is None  # same pattern: not a second lesson
        assert store.add_from_failure("missing_value", "q")["lesson_id"] == "lesson_002"
        store.save()
        assert len(json.loads((Path(tmp) / "lessons.json").read_text())) == 2
        assert len(LessonStore(Path(tmp) / "lessons.json").lessons) == 2


def test_relevant_lessons_are_loaded_by_similarity_and_counted_when_used():
    import cache_svc.embedding as embedding
    saved = embedding.embed
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = LessonStore(Path(tmp) / "lessons.json", min_similarity=0.5)
            lesson = store.add("pattern about unrelated questions", "say the catalogue cannot answer")
            table = {"pattern about unrelated questions": [1.0, 0.0], "Who is the president of France?": [0.9, 0.1], "How many seats in DATA-260?": [0.0, 1.0]}
            embedding.embed = lambda texts: [np.asarray(table[t]) / np.linalg.norm(table[t]) for t in texts]
            assert [row["lesson_id"] for row in store.relevant("Who is the president of France?")] == [lesson["lesson_id"]]
            assert store.relevant("How many seats in DATA-260?") == []
            model = ScriptedModel(["The catalogue cannot answer that."])
            answer = AnsweringAgent(model, lambda: ROWS, store).answer("Who is the president of France?")
            assert answer["lessons_used"] == [lesson["lesson_id"]] and store.lessons[0]["use_count"] == 1
            assert "say the catalogue cannot answer" in model.prompts[0][0][1]
    finally:
        embedding.embed = saved


def result_row(i, passed, failure=None):
    return {"id": i, "final_result": "PASS" if passed else "REVISE", "final_failure_type": failure}


def test_validation_keeps_a_lesson_that_fixes_failures_without_regressions():
    before = [result_row("a", True), result_row("b", False, "unsupported_answer")]
    after = [result_row("a", True), result_row("b", True)]
    decision = validation_decision(before, after)
    assert decision["keep"] and decision["fixed"] == ["b"] and decision["regressed"] == []


def test_validation_rejects_a_lesson_that_breaks_a_correct_answer():
    before = [result_row("a", True), result_row("b", False, "unsupported_answer")]
    after = [result_row("a", False, "wrong_decline"), result_row("b", True)]
    decision = validation_decision(before, after)
    assert not decision["keep"] and decision["regressed"] == ["a"]


def test_validation_rejects_more_unsupported_answers_and_keeps_an_unchanged_result():
    before = [result_row("a", True), result_row("b", False, "wrong_value")]
    more_unsupported = [result_row("a", True), result_row("b", False, "unsupported_answer")]
    assert not validation_decision(before, more_unsupported)["keep"]
    assert validation_decision(before, before)["keep"]  # unchanged failures are allowed by the assignment


def test_summary_counts_correct_attempts_and_latency():
    results = [{"final_result": "PASS", "attempt_count": 1, "latency_s": 2.0}, {"final_result": "REVISE", "attempt_count": 2, "latency_s": 6.0}]
    assert summarize(results) == {"questions": 2, "correct": 1, "incorrect": 1, "average_attempts": 1.5, "average_latency_s": 4.0}


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    logging.disable(logging.CRITICAL)
    failed = 0
    started = time.time()
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - report every failing test
            failed += 1
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed ({time.time() - started:.1f}s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
