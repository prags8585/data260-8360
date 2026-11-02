import json
import logging
import sys
import tempfile
import time
from argparse import Namespace
from pathlib import Path

from fastapi.testclient import TestClient

import writer
from kafka_svc import api, brains, bus, config
from kafka_svc.catalogue import gather_facts
from kafka_svc.course_logic import create_course, get_course, handle_operation, handle_request, validate_course
from kafka_svc.idempotency import ProcessedStore
from kafka_svc.ordering import analyse, make_messages

GOOD = {"courseTitle": "Cloud Computing", "courseCode": "DATA-270", "seatsAvailable": 40, "instructorId": 1}


# --- Part 1: course logic, envelope, configuration ----------------------------------------------------------

def test_configuration_follows_the_personal_values():
    assert config.PORT_BASE == 8260 and config.PREFIX == "s8360" and config.SEED == 8360 and config.VERIFY_SEED == 268360
    assert config.REQUEST_TOPIC == "s8360_entity_requests" and config.RESPONSE_TOPIC == "s8360_entity_responses"
    assert config.TOPIC_PARTITIONS[config.TASKS_TOPIC] == 2
    assert all(t.startswith("s8360_") for t in config.TOPIC_PARTITIONS)


def test_create_course_generates_a_uuid_and_stores_the_entity():
    store: dict = {}
    reply = create_course(store, GOOD)
    assert reply["success"] is True and reply["message"] == "Course created"
    assert len(reply["course_id"]) == 36 and reply["course_id"] in store
    assert store[reply["course_id"]]["courseCode"] == "DATA-270"


def test_create_then_get_round_trip():
    store: dict = {}
    created = create_course(store, GOOD)
    fetched = get_course(store, {"course_id": created["course_id"]})
    assert fetched["success"] is True and fetched["course"]["course_id"] == created["course_id"]
    assert fetched["course"]["courseTitle"] == "Cloud Computing"


def test_get_unknown_course_is_a_clean_error():
    assert get_course({}, {"course_id": "nope"}) == {"success": False, "error": "Course not found"}
    assert get_course({}, {})["success"] is False


def test_missing_empty_and_invalid_fields_are_rejected():
    bad = [
        {k: v for k, v in GOOD.items() if k != "seatsAvailable"},
        {**GOOD, "courseTitle": "   "},
        {**GOOD, "courseCode": "data260"},
        {**GOOD, "seatsAvailable": -1},
        {**GOOD, "seatsAvailable": True},
        {**GOOD, "seatsAvailable": "40"},
        {**GOOD, "instructorId": 0},
        {**GOOD, "surprise": 1},
        "not an object",
        None,
    ]
    for data in bad:
        course, error = validate_course(data)
        assert course is None and error, data
    assert validate_course({**GOOD, "department": "Data Science"})[0]["department"] == "Data Science"


def test_unknown_operation_is_rejected():
    assert handle_operation({}, "DELETE_COURSE", {}) == {"success": False, "error": "Unknown operation"}


def test_every_response_keeps_the_correlation_id():
    store: dict = {}
    for operation, data in (("CREATE_COURSE", GOOD), ("CREATE_COURSE", {}), ("GET_COURSE", {"course_id": "x"}), ("NOPE", {})):
        reply = handle_request(store, {"correlation_id": "abc-123", "reply_to": config.RESPONSE_TOPIC, "operation": operation, "data": data})
        assert reply["correlation_id"] == "abc-123" and isinstance(reply["success"], bool)


def test_requests_without_a_correlation_id_get_an_error_not_a_crash():
    assert handle_request({}, {"operation": "CREATE_COURSE", "data": GOOD})["success"] is False
    assert handle_request({}, None)["success"] is False
    assert handle_request({}, ["list"])["correlation_id"] is None


# --- the FastAPI wrapper -------------------------------------------------------------------------------------

class FakeRpc:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def call(self, operation, data, correlation_id=None, timeout=10.0):
        self.calls.append((operation, data, correlation_id))
        return {"correlation_id": correlation_id, **self.reply}


def api_client(reply=None) -> TestClient:
    api.app.state.direct_store = {}
    api.app.state.client = FakeRpc(reply or {"success": True, "course_id": "11111111-1111-1111-1111-111111111111", "message": "Course created"})
    return TestClient(api.app)


def test_api_forwards_the_callers_correlation_id_to_kafka():
    client = api_client()
    reply = client.post("/courses", json=GOOD, headers={"X-Correlation-ID": "corr-1"})
    assert reply.status_code == 201 and reply.headers["x-correlation-id"] == "corr-1" and reply.json()["correlation_id"] == "corr-1"
    assert api.app.state.client.calls == [("CREATE_COURSE", GOOD, "corr-1")]


def test_api_generates_a_correlation_id_when_none_is_supplied():
    reply = api_client().post("/courses", json=GOOD)
    assert reply.status_code == 201 and len(reply.headers["x-correlation-id"]) == 36


def test_api_maps_worker_errors_to_http_codes():
    assert api_client({"success": False, "error": "Course not found"}).get("/courses/x").status_code == 404
    assert api_client({"success": False, "error": "courseTitle must be a non-empty string"}).post("/courses", json=GOOD).status_code == 422
    assert api_client({"success": False, "error": "No response from worker within 10s"}).post("/courses", json=GOOD).status_code == 504


# --- Part 2: agent logic --------------------------------------------------------------------------------------

def test_rule_writer_output_passes_the_reviewer():
    question = "Which department has the most available seats, and which course there has the most seats?"
    draft, facts = brains.write_draft("rule", None, question, brains.plan_rule(question))
    review = brains.review_draft(question, draft, facts)
    assert review["approved"] and "Data Science" in draft and "DATA-260" in draft


def test_reviewer_rejects_a_wrong_course_and_an_invented_number():
    question = "Which department has the most available seats, and which course there has the most seats?"
    facts = gather_facts(question)
    wrong = "Data Science has the most seats and its largest course is DATA-245."
    invented = "Data Science has the most seats (999 in total); its largest course is DATA-260."
    for draft, failed in ((wrong, "superlative_correct"), (invented, "numbers_grounded")):
        review = brains.review_draft(question, draft, facts)
        assert not review["approved"]
        assert failed in [c["check"] for c in review["checks"] if not c["passed"]]


def test_facts_come_from_the_hw5_tools():
    facts = gather_facts("anything")
    assert facts["totals"] == {"courses": 6, "seats": 260} and len(facts["courses"]) == 6
    assert {g["group"] for g in facts["departments"]} == {"Computer Science", "Data Science", "Statistics"}


# --- Part 3: failure behaviour --------------------------------------------------------------------------------

class FakeMsg:
    def __init__(self, value, offset=0, key=None):
        self._value, self._offset, self._key = value, offset, key

    def topic(self): return config.TASKS_TOPIC
    def partition(self): return 0
    def offset(self): return self._offset
    def value(self): return self._value
    def key(self): return self._key


class FakeConsumer:
    def __init__(self):
        self.committed = []

    def commit(self, message=None, asynchronous=False):
        self.committed.append(message.offset())


def writer_args(**over) -> Namespace:
    return Namespace(**{"id": "w", "brain": "rule", "max_attempts": 3, "dlq": True, "auto_commit": False, **over})


def run_writer(monkeypatch_sends, msgs, args, processed):
    consumer, sent, dead = FakeConsumer(), monkeypatch_sends["sent"], monkeypatch_sends["dead"]
    for m in msgs:
        writer.handle(m, args, None, object(), consumer, processed, None)
    return consumer, sent, dead


def patched_writer():
    sent, dead = [], []
    writer.send = lambda producer, topic, value, key=None, **kw: (sent.append((topic, value)) or (0, len(sent) - 1))
    writer.dead_letter = lambda producer, msg, error, attempts: (dead.append({"offset": msg.offset(), "error": error, "attempts": attempts}) or (0, len(dead) - 1))
    writer.time.sleep = lambda s: None
    return {"sent": sent, "dead": dead}


def task_bytes(cid):
    return json.dumps({"correlation_id": cid, "question": "q", "plan": ["a"]}).encode()


def test_writer_commits_only_after_the_draft_is_sent():
    hooks = patched_writer()
    consumer, sent, _ = run_writer(hooks, [FakeMsg(task_bytes("c1"), 7)], writer_args(), None)
    assert [t for t, _ in sent] == [config.DRAFTS_TOPIC] and consumer.committed == [7]


def test_idempotent_writer_skips_a_replayed_correlation_id():
    hooks = patched_writer()
    with tempfile.TemporaryDirectory() as d:
        store = ProcessedStore(Path(d) / "p.sqlite")
        consumer, sent, _ = run_writer(hooks, [FakeMsg(task_bytes("same"), 1), FakeMsg(task_bytes("same"), 2)], writer_args(), store)
    assert len(sent) == 1 and consumer.committed == [1, 2]


def test_writer_without_idempotency_repeats_the_side_effect():
    hooks = patched_writer()
    _, sent, _ = run_writer(hooks, [FakeMsg(task_bytes("same"), 1), FakeMsg(task_bytes("same"), 2)], writer_args(), None)
    assert len(sent) == 2


def test_poison_message_is_retried_three_times_then_dead_lettered_and_skipped():
    hooks = patched_writer()
    attempts = []
    original = writer.produce_draft
    writer.produce_draft = lambda *a, **k: (attempts.append(1), original(*a, **k))[1]
    try:
        consumer, sent, dead = run_writer(hooks, [FakeMsg(b'{"correlation_id": "p", "qu', 5), FakeMsg(task_bytes("good"), 6)], writer_args(), None)
    finally:
        writer.produce_draft = original
    assert dead == [{"offset": 5, "error": "ValueError: task is not valid JSON", "attempts": 3}]
    assert len(sent) == 1 and consumer.committed == [5, 6]


def test_writer_without_dead_letter_raises_and_leaves_the_offset_uncommitted():
    hooks = patched_writer()
    consumer = FakeConsumer()
    try:
        writer.handle(FakeMsg(b"{broken", 3), writer_args(max_attempts=1, dlq=False), None, object(), consumer, None, None)
    except ValueError:
        pass
    else:
        raise AssertionError("expected the bad message to raise")
    assert consumer.committed == [] and hooks["sent"] == []


def test_auto_commit_mode_never_commits_by_hand():
    hooks = patched_writer()
    consumer, _, _ = run_writer(hooks, [FakeMsg(task_bytes("a"), 1)], writer_args(auto_commit=True), None)
    assert consumer.committed == []


def test_processed_store_survives_a_restart():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "p.sqlite"
        first = ProcessedStore(path)
        assert first.mark("x", "w1") is True and first.mark("x", "w2") is False
        first.close()
        assert ProcessedStore(path).seen("x") and not ProcessedStore(path).seen("y")


def test_dead_letter_record_keeps_the_source_position_and_original_bytes():
    sent = []
    bus.send = lambda producer, topic, value, key=None, **kw: (sent.append((topic, value, key)) or (0, 0))
    bus.dead_letter(object(), FakeMsg(b'{"correlation_id": "p", "qu', 9, key=b"p"), "ValueError: boom", 3)
    topic, record, key = sent[0]
    assert topic == config.DEAD_LETTER_TOPIC and key == "p"
    assert (record["source_offset"], record["attempts"], record["correlation_id"]) == (9, 3, "p")
    assert record["original_value"] == '{"correlation_id": "p", "qu'


def test_ordering_messages_are_seeded_and_numbered_per_entity():
    a, b = make_messages(config.VERIFY_SEED), make_messages(config.VERIFY_SEED)
    assert a == b and len(a) == 20 and make_messages(1) != a
    for entity in {m["entity"] for m in a}:
        assert [m["seq"] for m in a if m["entity"] == entity] == list(range(1, 1 + sum(1 for m in a if m["entity"] == entity)))


def test_ordering_analysis_finds_inversions_and_partition_spread():
    def rec(entity, seq, partition, t):
        return {"writer": f"w{partition}", "partition": partition, "offset": seq, "entity": entity, "seq": seq, "finished_at": t}
    broken = analyse([rec("A", 1, 0, "01"), rec("A", 3, 1, "02"), rec("A", 2, 0, "03")])
    assert broken["total_inversions"] == 1 and broken["entities_in_order"] == 0 and broken["entities_in_one_partition"] == 0
    fine = analyse([rec("A", 1, 0, "01"), rec("A", 2, 0, "02"), rec("B", 1, 1, "03")])
    assert fine["total_inversions"] == 0 and fine["entities_in_one_partition"] == 2


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    logging.disable(logging.CRITICAL)
    failed = 0
    started = time.time()
    for test in TESTS:
        saved = (writer.send, writer.dead_letter, bus.send, time.sleep)
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - report every failing test
            failed += 1
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
        finally:
            writer.send, writer.dead_letter, bus.send, time.sleep = saved
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed ({time.time() - started:.1f}s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
