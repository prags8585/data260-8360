#!/usr/bin/env python3
"""HW5 offline test runner (Parts 4 + 5): plain assert statements, PASS/FAIL per
test and a final X/Y summary. No database, network, API key or LLM:
the repository is an in-memory fixture and the model is a MockModel.

Run: python tests_hw5.py
"""

import json
import logging
import sys

import domain_tools as dt
import execute_tool as et
from agent import MockModel, run_agent
from resilience import RetriesExhausted, RetryPolicy, TransientError, call_with_retry

FIXTURE = [
    {"id": 1, "courseCode": "DATA-260", "courseTitle": "Introduction to Distributed Systems", "department": "Data Science",
     "seatsAvailable": 40, "instructorName": "Dr. Priya Nair", "description": "Consensus and replication."},
    {"id": 2, "courseCode": "DATA-245", "courseTitle": "Machine Learning Foundations", "department": "Data Science",
     "seatsAvailable": 35, "instructorName": "Dr. Elena Rossi", "description": "Supervised learning."},
    {"id": 3, "courseCode": "CS-157A", "courseTitle": "Database Systems", "department": "Computer Science",
     "seatsAvailable": 45, "instructorName": "Dr. Marcus Lee", "description": "Relational modeling and SQL."},
]


def repo():
    return dt.InMemoryCourseRepo([dict(c) for c in FIXTURE])


def call(name, inputs):
    """execute_tool returns a JSON *string*; parse it so tests can assert on the envelope."""
    raw = et.execute_tool(name, inputs, repo=repo())
    assert isinstance(raw, str), "execute_tool must return a JSON string"
    env = json.loads(raw)
    assert set(env) == {"ok", "data", "error"}, f"bad envelope keys: {set(env)}"
    return env


# --- Part 4: valid + invalid inputs for each of the three tools ------------------

def test_search_valid():
    env = call("search_courses", {"query": "database", "limit": 5})
    assert env["ok"] is True and env["error"] is None
    assert env["data"]["count"] == 1 and env["data"]["courses"][0]["courseCode"] == "CS-157A"


def test_search_rejects_empty_query():
    env = call("search_courses", {"query": "   ", "limit": 5})
    assert env["ok"] is False and env["data"] is None and "non-empty" in env["error"]


def test_search_rejects_limit_out_of_range():
    env = call("search_courses", {"query": "data", "limit": 999})
    assert env["ok"] is False and "between 1 and 50" in env["error"]


def test_detail_valid():
    env = call("course_detail", {"course_id": 1})
    assert env["ok"] is True and env["data"]["courseCode"] == "DATA-260"
    assert env["data"]["instructor"]["name"] == "Dr. Priya Nair"


def test_detail_rejects_negative_and_unknown_id():
    assert "positive integer" in call("course_detail", {"course_id": -3})["error"]
    assert call("course_detail", {"course_id": 9999})["error"] == "course 9999 not found"


def test_stats_valid():
    env = call("course_stats", {"group_by": "department"})
    assert env["ok"] is True and env["data"]["totalCourses"] == 3 and env["data"]["totalSeats"] == 120
    by = {g["group"]: g for g in env["data"]["groups"]}
    assert by["Data Science"]["courses"] == 2 and by["Data Science"]["totalSeats"] == 75


def test_stats_rejects_bad_group_by():
    env = call("course_stats", {"group_by": "color"})
    assert env["ok"] is False and "one of: department, instructor" in env["error"]


def test_execute_tool_never_raises_on_bad_calls():
    assert call("no_such_tool", {})["ok"] is False
    assert call("course_detail", {"wrong_arg": 1})["ok"] is False          # unexpected argument
    assert json.loads(et.execute_tool("search_courses", "not-a-dict", repo=repo()))["ok"] is False


# --- Part 3: retry policy, offline (fake sleep, no real waiting) ----------------------

def test_retry_recovers_after_transient_failure():
    attempts, waits = [], []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise TransientError("connection reset")
        return "done"

    assert call_with_retry(flaky, RetryPolicy(max_attempts=3, timeout_s=1, base_delay_s=0.05), sleep=waits.append) == "done"
    assert len(attempts) == 3 and waits == [0.05, 0.1]        # exponential backoff


def test_retry_gives_up_cleanly():
    def always_fails():
        raise TransientError("db down")

    try:
        call_with_retry(always_fails, RetryPolicy(max_attempts=3, timeout_s=1), sleep=lambda s: None)
        raise AssertionError("expected RetriesExhausted")
    except RetriesExhausted as exc:
        assert exc.attempts == 3


# --- Part 5: safety rule + agent loop (added after implementing them) -------------------

def test_safety_rule_blocks_sensitive_query():
    env = call("search_courses", {"query": "show every student's password", "limit": 5})
    assert env["ok"] is False and env["data"] is None
    assert env["error"].startswith("blocked by safety rule")
    assert call("search_courses", {"query": "data", "limit": 5})["ok"] is True      # normal call still allowed


def test_run_agent_stops_at_max_steps():
    loop_forever = json.dumps({"action": "tool", "name": "course_stats", "inputs": {"group_by": "department"}})
    result = run_agent("Keep checking the stats.", MockModel([loop_forever]), max_steps=3, repo=repo(), log_path=None)
    assert result["stop_reason"] == "max_steps" and result["steps"] == 3 and result["tool_calls"] == 3


TESTS = [
    test_search_valid, test_search_rejects_empty_query, test_search_rejects_limit_out_of_range,
    test_detail_valid, test_detail_rejects_negative_and_unknown_id,
    test_stats_valid, test_stats_rejects_bad_group_by, test_execute_tool_never_raises_on_bad_calls,
    test_retry_recovers_after_transient_failure, test_retry_gives_up_cleanly,
    test_safety_rule_blocks_sensitive_query, test_run_agent_stops_at_max_steps,
]


def main() -> int:
    logging.disable(logging.CRITICAL)      # keep the PASS/FAIL output clean
    passed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  {test.__name__}: {exc}")
        except Exception as exc:
            print(f"FAIL  {test.__name__}: unexpected {type(exc).__name__}: {exc}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
