#!/usr/bin/env python3
"""HW9 Part 4: self-improving two-agent system (Answering Agent + Evaluator Agent).

  mine      baseline answers on training_data.json; every failure pattern the Evaluator finds becomes a candidate lesson
  validate  keep a candidate lesson only if validation_data.json does not get worse (4.3)
  demo      one complete revision sequence (controlled flawed first answer) and one lesson created after a single failure and reused (4.1, 4.2)
  final     the four variants on test_data.json (4.4); the test set is used for nothing else
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from kafka_svc.catalogue import mysql_courses
from selfimprove.answering import AnsweringAgent
from selfimprove.evaluator import EvaluatorAgent
from selfimprove.lessons import LessonStore
from selfimprove.pipeline import load_questions, run_question, run_set, summarize, validation_decision
from selfimprove.reference import Reference

ROOT = Path(__file__).resolve().parent.parent
PART4 = ROOT / "part4"
RAW = ROOT / "reports/hw09/raw"
MODEL, SEED = "qwen3:8b", 8360
OVERBROAD = ("If you are not completely sure of an answer, do not answer; reply that you do not have that information.",
             "Whenever there is any doubt, say that you do not have the information instead of answering.")


def make_agents(lessons: LessonStore | None):
    from src.model_client import ModelClient
    model = ModelClient(model=MODEL, temperature=0.0, seed=SEED, num_predict=200)
    return AnsweringAgent(model, mysql_courses, lessons), EvaluatorAgent(Reference())


def line(r: dict) -> None:
    flag = "PASS  " if r["final_result"] == "PASS" else "REVISE"
    print(f"  {r['id']} {flag} attempts={r['attempt_count']} {r['latency_s']:>5.1f}s  [{r['kind']}] {r['question']}")
    print(f"        -> {r['final_answer']}" + (f"   (failure: {r['final_failure_type']})" if r["final_failure_type"] else ""))


def save(name: str, data) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / name).write_text(json.dumps(data, indent=2))
    print(f"saved reports/hw09/raw/{name}")


def stage_mine() -> int:
    train = load_questions(PART4 / "training_data.json")
    answering, evaluator = make_agents(None)
    print(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} === mine lessons: baseline Answering Agent on {len(train)} training questions (no lessons, no revision)")
    results = run_set(train, answering, evaluator, repair=False, log=line)
    counts: dict[str, list[str]] = {}
    for r in results:
        if r["final_failure_type"]:
            counts.setdefault(f"{r['final_failure_type']}:{r['kind']}", []).append(r["id"])
    candidates = LessonStore(PART4 / "lessons_candidates.json")
    candidates.lessons = []
    print("\nfailure patterns found (a pattern seen at least twice is a repeated failure):")
    for failure_type, ids in sorted(counts.items(), key=lambda kv: -len(kv[1])):
        example = next(r["question"] for r in results if r["id"] == ids[0])
        kind_of_failure, kind = failure_type.split(":")
        lesson = candidates.add_from_failure(kind_of_failure, example, kind=kind)
        print(f"  {failure_type:20} x{len(ids)}  {ids}  -> {lesson['lesson_id'] if lesson else '-'}")
    candidates.save()
    print(f"\n{len(candidates.lessons)} candidate lessons written to part4/lessons_candidates.json")
    save("part4_mine.json", {"summary": summarize(results), "failures": counts, "results": results, "candidates": candidates.lessons})
    return 0


def stage_validate(with_overbroad: bool) -> int:
    validation = load_questions(PART4 / "validation_data.json")
    candidates = LessonStore(PART4 / "lessons_candidates.json").lessons
    accepted = LessonStore(PART4 / "lessons.json")
    accepted.lessons = []
    if with_overbroad:
        candidates = candidates + [{"lesson_id": "lesson_x01", "failure_pattern": OVERBROAD[0], "correction": OVERBROAD[1], "created_at": "controlled", "use_count": 0}]
    answering, evaluator = make_agents(accepted)
    print(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} === validate {len(candidates)} candidate lessons on {len(validation)} validation questions (single attempt, no revision)")
    current = run_set(validation, answering, evaluator, repair=False)
    print(f"before any lesson: {summarize(current)['correct']}/{len(validation)} correct")
    log = []
    for candidate in candidates:
        trial = LessonStore(PART4 / "lessons.json")
        trial.lessons = [dict(lesson) for lesson in accepted.lessons] + [dict(candidate)]
        answering.lessons = trial
        after = run_set(validation, answering, evaluator, repair=False)
        decision = validation_decision(current, after)
        keep = decision["keep"]
        reason = (("kept" if keep else "rejected") + f": fixed {decision['fixed'] or 'none'}, regressed {decision['regressed'] or 'none'}, "
                  f"failing {decision['failing_before']} -> {decision['failing_after']}, "
                  f"unsupported answers {decision['unsupported_before']} -> {decision['unsupported_after']}")
        print(f"\n{candidate['lesson_id']} ({candidate['failure_pattern'][:70]}...)\n  {reason}")
        log.append({"lesson": candidate, **decision, "results_after": after})
        if keep:
            accepted.lessons.append(dict(candidate))
            current = after
    for n, lesson in enumerate(accepted.lessons, 1):
        lesson["lesson_id"] = f"lesson_{n:03d}"
        lesson["use_count"] = 0
    accepted.save()
    print(f"\nkept {len(accepted.lessons)} of {len(candidates)} lessons -> part4/lessons.json; validation now {summarize(current)['correct']}/{len(validation)} correct")
    save("part4_validation.json", {"candidates": len(candidates), "kept": len(accepted.lessons), "log": log})
    return 0


def stage_demo() -> int:
    answering, evaluator = make_agents(None)
    print(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} === 4.1 one complete revision sequence (controlled: the first answer is made incomplete on purpose)")
    flawed = "DATA-260 still has seats available."
    item = {"id": "controlled", "question": "How many seats are available in DATA-260?"}
    result = run_question(item, answering, evaluator, repair=True, max_attempts=2, forced_first=flawed)
    print(f"question: {item['question']}")
    for a in result["attempts"]:
        ev = a["evaluation"]
        print(f"\nattempt {ev['attempt']}: answer   : {a['answer']}")
        print(f"           evaluator: {ev['result']} - {ev['explanation']}")
        if ev["feedback"]:
            print(f"           feedback : {ev['feedback']}")
    print(f"\nattempts: {result['attempt_count']}   final answer: {result['final_answer']}   final evaluation: {result['final_result']}")

    print("\n=== 4.2 a lesson created after ONE failed answer is loaded and reused for a later related question ===")
    with tempfile.TemporaryDirectory() as tmp:
        store = LessonStore(Path(tmp) / "lessons.json")
        answering.lessons = store
        first = {"id": "first", "question": "Is CS-146 a fun course?"}
        r1 = run_question(first, answering, evaluator, repair=False)
        print(f"first question : {first['question']}\n  answer       : {r1['final_answer']}\n  evaluator    : {r1['attempts'][0]['evaluation']['result']} - {r1['attempts'][0]['evaluation']['explanation']}")
        if not r1["final_failure_type"]:
            print("  (the first answer passed, so no lesson is created - pick another demonstration question)")
            return 1
        lesson = store.add_from_failure(r1["final_failure_type"], first["question"], kind=r1["kind"])
        store.save()
        print("  lesson created and saved to lessons.json:")
        print("  " + json.dumps(lesson, indent=2).replace("\n", "\n  "))
        later = {"id": "later", "question": "Which Data Science course is the easiest to pass?"}
        r2 = run_question(later, answering, evaluator, repair=False)
        print(f"\nlater, related question : {later['question']}")
        print(f"  lessons loaded before answering: {r2['attempts'][0]['lessons_used']}")
        print(f"  answer       : {r2['final_answer']}\n  evaluator    : {r2['attempts'][0]['evaluation']['result']} - {r2['attempts'][0]['evaluation']['explanation']}")
        print(f"  use_count of {lesson['lesson_id']} in lessons.json is now {store.lessons[0]['use_count']}")
        answering.lessons = LessonStore(Path(tmp) / "empty.json")
        control = run_question(later, answering, evaluator, repair=False)
        print(f"  control, same question without any lesson: {control['final_answer']}\n  evaluator    : {control['attempts'][0]['evaluation']['result']} - {control['attempts'][0]['evaluation']['explanation']}")
        save("part4_demo.json", {"revision": result, "lesson": lesson, "first": r1, "later": r2, "use_count_after": store.lessons[0]["use_count"], "control_without_lesson": control})
    return 0


def stage_final() -> int:
    test = load_questions(PART4 / "test_data.json")
    print(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} === final evaluation: four variants on the same {len(test)} test questions")
    variants = [
        ("Baseline", None, False),
        ("Evaluator Repair", None, True),
        ("Lesson Memory", PART4 / "lessons_candidates.json", True),
        ("Validated Improvement", PART4 / "lessons.json", True),
    ]
    report = {}
    for name, lesson_file, repair in variants:
        store = LessonStore(lesson_file) if lesson_file else None
        answering, evaluator = make_agents(store)
        print(f"\n-- {name}: lessons={'none' if store is None else f'{len(store.lessons)} from {lesson_file.name}'}, evaluator feedback and revision={'on' if repair else 'off'}")
        results = run_set(test, answering, evaluator, repair=repair, log=line)
        report[name] = {"summary": summarize(results), "lessons": 0 if store is None else len(store.lessons), "results": results}
        if store is not None:
            store.save()
    print("\nVariant                  Correct  Incorrect  Avg attempts  Avg latency")
    for name, data in report.items():
        s = data["summary"]
        print(f"{name:24} {s['correct']:>5}/{s['questions']}  {s['incorrect']:>8}  {s['average_attempts']:>11}  {s['average_latency_s']:>8}s")
    save("part4_final.json", report)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["mine", "validate", "demo", "final"])
    parser.add_argument("--with-overbroad", action="store_true", help="validate: also test one deliberately over-broad lesson (controlled regression check)")
    args = parser.parse_args()
    if args.stage == "mine":
        return stage_mine()
    if args.stage == "validate":
        return stage_validate(args.with_overbroad)
    return stage_demo() if args.stage == "demo" else stage_final()


if __name__ == "__main__":
    sys.exit(main())
