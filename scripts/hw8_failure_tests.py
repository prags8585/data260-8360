#!/usr/bin/env python3
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from kafka_svc import config
from kafka_svc.bus import make_producer, send
from kafka_svc.ordering import analyse, make_messages
from kafka_svc.probe import end_offsets, group_offsets, read_since, seed_group

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "reports" / "hw08" / "raw"
LOGS = RAW / "logs"
STATE = ROOT / "kafka_state"
PLAN = ["Identify the needed facts", "Look them up", "Answer from the facts"]


def say(text: str = "") -> None:
    print(text, flush=True)


def excerpt(text: str, *needles: str) -> None:
    for line in text.splitlines():
        if any(n in line for n in needles):
            say("    " + re.sub(r" message=\{.*", " message={...}", line)[:230])


class Writer:
    def __init__(self, tag: str, writer_id: str, group: str, flags: list[str], state_db: Path, trace: Path | None = None):
        self.log_path = LOGS / f"t3_{tag}.log"
        self.cmd = [sys.executable, "-u", "writer.py", "--id", writer_id, "--brain", "rule", "--group", group,
                    "--state-db", str(state_db), *flags]
        if trace:
            self.cmd += ["--trace-file", str(trace)]
        self.proc: subprocess.Popen | None = None
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("")
        self.start()

    def start(self, marker: str | None = None) -> None:
        with open(self.log_path, "a") as handle:
            if marker:
                handle.write(f"----- {marker} -----\n")
            self.proc = subprocess.Popen(self.cmd, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                         env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"})

    def text(self) -> str:
        return self.log_path.read_text()

    def count(self, needle: str) -> int:
        return self.text().count(needle)

    def wait_for(self, needle: str, timeout: float = 30, count: int = 1) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.count(needle) >= count:
                return True
            time.sleep(0.2)
        return False

    def wait_exit(self, timeout: float = 20) -> int | None:
        try:
            return self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            return None

    def kill(self) -> None:
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait()

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def show_offsets(label: str, offsets: dict) -> None:
    say(f"  {label}")
    for line in offsets["raw"].splitlines():
        if line.strip() and "Warning" not in line:
            say("    " + line)


def task(cid: str, **extra) -> dict:
    return {"correlation_id": cid, "question": "Which department has the most seats?", "plan": PLAN, **extra}


def drafts_for(start: dict[int, int], needle: str) -> list[dict]:
    return [m for m in read_since(config.DRAFTS_TOPIC, start) if needle in m["value"]]


def run_duplicate(run_id: str) -> dict:
    say("=== Part 3 / I. Duplicate delivery: the same correlation_id delivered twice ===")
    result: dict = {}
    for phase, flags in (("before", ["--no-idempotency"]), ("after", [])):
        group = f"{config.WRITER_GROUP}_dup_{phase}_{run_id}"
        seed_group(group, config.TASKS_TOPIC)
        drafts_start = end_offsets(config.DRAFTS_TOPIC)
        cid = f"dup-{phase}-{run_id}"
        writer = Writer(f"duplicate_{phase}", "writer-dup", group, flags, STATE / f"dup_{phase}_{run_id}.sqlite")
        writer.wait_for("assigned partitions", 40)
        say(f"-- {phase} fix: writer flags {flags or '(idempotency on)'}, correlation_id {cid}")
        producer = make_producer("failure-test")
        payload = json.dumps(task(cid)).encode()
        p1, o1 = send(producer, config.TASKS_TOPIC, payload, key=cid)
        writer.wait_for("committed offset", 20)
        p2, o2 = send(producer, config.TASKS_TOPIC, payload, key=cid)
        say(f"   sent the task at partition={p1} offset={o1}, replayed the identical message at partition={p2} offset={o2}")
        writer.wait_for("committed offset", 20, count=2)
        writer.stop()
        drafts = drafts_for(drafts_start, cid)
        excerpt(writer.text(), "received task", "DUPLICATE", "draft acknowledged", "committed offset")
        say(f"   drafts on {config.DRAFTS_TOPIC} for this correlation_id: {len(drafts)}")
        result[phase] = {"flags": flags, "correlation_id": cid, "deliveries": 2, "drafts_published": len(drafts),
                         "duplicate_skipped": writer.count("DUPLICATE"), "log": str(writer.log_path.relative_to(ROOT))}
    return result


def run_death(run_id: str) -> dict:
    say("=== Part 3 / II. Consumer death: Writer killed (SIGKILL) while it is processing ===")
    result: dict = {}
    for phase, flags in (("before", ["--auto-commit"]), ("after", [])):
        group = f"{config.WRITER_GROUP}_death_{phase}_{run_id}"
        seed_group(group, config.TASKS_TOPIC)
        drafts_start = end_offsets(config.DRAFTS_TOPIC)
        cid = f"death-{phase}-{run_id}"
        state = STATE / f"death_{phase}_{run_id}.sqlite"
        writer = Writer(f"death_{phase}", "writer-death", group, flags, state)
        writer.wait_for("assigned partitions", 40)
        say(f"-- {phase} fix: writer flags {flags or '(commit after processing)'}, task needs 8 s of work, correlation_id {cid}")
        partition, offset = send(make_producer("failure-test"), config.TASKS_TOPIC, task(cid, work_ms=8000, test="consumer-death"), key=cid)
        writer.wait_for(f"processing correlation_id={cid}", 20)
        time.sleep(2.5)
        say(f"   task at partition={partition} offset={offset}; writer is mid-processing, sending SIGKILL now")
        writer.kill()
        time.sleep(1)
        after_kill = group_offsets(group)
        show_offsets("offsets right after the kill:", after_kill)
        drafts_after_kill = len(drafts_for(drafts_start, cid))
        say(f"   drafts for this correlation_id after the kill: {drafts_after_kill}")

        say("   restarting the writer (same group)")
        writer.start(marker="writer restarted")
        writer.wait_for("assigned partitions", 40, count=2)
        redelivered = writer.wait_for(f"received task from {config.TASKS_TOPIC} partition={partition} offset={offset} correlation_id={cid}",
                                      25 if phase == "after" else 12, count=2)
        if redelivered:
            writer.wait_for("draft acknowledged", 30)
            writer.wait_for("committed offset", 10)
        writer.stop()
        final = group_offsets(group)
        show_offsets("offsets after the restart:", final)
        drafts_final = len(drafts_for(drafts_start, cid))
        excerpt(writer.text(), "assigned partitions", "received task", "processing correlation_id", "draft acknowledged", "committed offset")
        say(f"   redelivered after restart: {redelivered}; drafts for this correlation_id: {drafts_final}")
        result[phase] = {"flags": flags, "correlation_id": cid, "offsets_after_kill": after_kill, "drafts_after_kill": drafts_after_kill,
                         "redelivered_after_restart": redelivered, "offsets_after_restart": final, "drafts_final": drafts_final,
                         "log": str(writer.log_path.relative_to(ROOT))}
    return result


def run_poison(run_id: str) -> dict:
    say("=== Part 3 / III. Poison message: a malformed task followed by a good one ===")
    result: dict = {}
    for phase, flags in (("before", ["--no-dlq"]), ("after", [])):
        group = f"{config.WRITER_GROUP}_poison_{phase}_{run_id}"
        seed_group(group, config.TASKS_TOPIC)
        drafts_start, dlq_start = end_offsets(config.DRAFTS_TOPIC), end_offsets(config.DEAD_LETTER_TOPIC)
        bad_cid, good_cid = f"poison-{phase}-{run_id}", f"after-poison-{phase}-{run_id}"
        producer = make_producer("failure-test")
        bad = f'{{"correlation_id": "{bad_cid}", "question": '.encode()
        say(f"-- {phase} fix: writer flags {flags or '(3 attempts, then dead-letter)'}")
        p_bad = send(producer, config.TASKS_TOPIC, bad, key=bad_cid, partition=0)
        p_good = send(producer, config.TASKS_TOPIC, task(good_cid), key=good_cid, partition=0)
        say(f"   poison message at partition/offset {p_bad}, good message right behind it at {p_good}")
        writer = Writer(f"poison_{phase}", "writer-poison", group, flags, STATE / f"poison_{phase}_{run_id}.sqlite")
        entry: dict = {"flags": flags, "poison_correlation_id": bad_cid, "good_correlation_id": good_cid}
        if phase == "before":
            entry["first_run_exit_code"] = writer.wait_exit(40)
            say(f"   writer run 1 exited with code {entry['first_run_exit_code']}; restarting it")
            writer.start(marker="writer restarted")
            entry["second_run_exit_code"] = writer.wait_exit(40)
            say(f"   writer run 2 exited with code {entry['second_run_exit_code']} (same message, same crash)")
            entry["offsets"] = group_offsets(group)
            show_offsets("offsets after two crashes:", entry["offsets"])
            entry["good_message_processed"] = len(drafts_for(drafts_start, good_cid)) > 0
            excerpt(writer.text(), "received task", "Traceback", "ValueError:", "committed offset", "----- writer restarted")
        else:
            writer.wait_for("committed offset", 40, count=2)
            time.sleep(1)
            entry["offsets"] = group_offsets(group)
            writer.stop()
            dead = [m for m in read_since(config.DEAD_LETTER_TOPIC, dlq_start) if bad_cid in m["value"]]
            entry["dead_letter_records"] = [json.loads(m["value"]) for m in dead]
            entry["good_message_processed"] = len(drafts_for(drafts_start, good_cid)) > 0
            entry["attempt_lines"] = writer.count("attempt ")
            excerpt(writer.text(), "received task", "processing correlation_id", "attempt ", "gave up", "draft acknowledged", "committed offset")
            show_offsets("offsets after the run:", entry["offsets"])
            say(f"   dead-letter record: {json.dumps(entry['dead_letter_records'][0])[:300] if dead else 'none'}")
        say(f"   good message processed: {entry['good_message_processed']}")
        entry["log"] = str(writer.log_path.relative_to(ROOT))
        result[phase] = entry
        writer.stop()
    return result


def assigned(writer: Writer) -> list[int] | None:
    found = re.findall(r"assigned partitions \[(.*?)\]", writer.text())
    return [int(x) for x in found[-1].split(",") if x.strip()] if found else None


def run_ordering(run_id: str) -> dict:
    say(f"=== Part 3 / IV. Ordering: 20 related messages (VERIFY_SEED {config.VERIFY_SEED}), 2 partitions, 2 writers in one group ===")
    messages = make_messages(config.VERIFY_SEED)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "ordering_messages.json").write_text(json.dumps(messages, indent=2))
    say("   entities and message counts: " + ", ".join(f"{e}={sum(1 for m in messages if m['entity'] == e)}" for e in sorted({m['entity'] for m in messages})))
    result: dict = {}
    for phase, keyed in (("before", False), ("after", True)):
        group = f"{config.WRITER_GROUP}_order_{phase}_{run_id}"
        seed_group(group, config.TASKS_TOPIC)
        traces = {w: STATE / f"order_{phase}_{run_id}_{w}.jsonl" for w in ("A", "B")}
        for t in traces.values():
            t.unlink(missing_ok=True)
        writers = {w: Writer(f"ordering_{phase}_{w}", f"writer-{w}", group, [], STATE / f"order_{phase}_{run_id}.sqlite", traces[w]) for w in ("A", "B")}
        deadline = time.time() + 60
        while time.time() < deadline:
            a, b = assigned(writers["A"]), assigned(writers["B"])
            if a and b and len(a) == 1 and len(b) == 1 and a != b:
                break
            time.sleep(0.3)
        say(f"-- {phase} fix: message key = {'entity (course code)' if keyed else 'none'}; writer-A owns partition {assigned(writers['A'])}, writer-B owns {assigned(writers['B'])}")
        producer = make_producer("failure-test")
        sent = []
        for m in messages:
            partition, offset = send(producer, config.TASKS_TOPIC, m, key=m["entity"] if keyed else None)
            sent.append({"correlation_id": m["correlation_id"], "entity": m["entity"], "seq": m["seq"], "partition": partition, "offset": offset})
        deadline = time.time() + 90
        trace: list[dict] = []
        while time.time() < deadline and len(trace) < len(messages):
            trace = [json.loads(line) for t in traces.values() if t.exists() for line in t.read_text().splitlines() if line.strip()]
            time.sleep(0.5)
        for w in writers.values():
            w.stop()
        analysis = analyse(trace)
        say(f"   {analysis['messages_processed']} messages processed; entities kept in one partition: {analysis['entities_in_one_partition']}/{len(analysis['entities'])}; "
            f"entities processed in order: {analysis['entities_in_order']}/{len(analysis['entities'])}; order inversions: {analysis['total_inversions']}")
        for entity, info in analysis["entities"].items():
            say(f"     {entity:9s} partitions={info['partitions']} writers={info['writers']} processed seq order={info['processed_seqs']} in_order={info['in_order']}")
        result[phase] = {"keyed": keyed, "sent": sent, "analysis": analysis,
                         "logs": [str(w.log_path.relative_to(ROOT)) for w in writers.values()]}
    return result


SCENARIOS = {"duplicate": run_duplicate, "death": run_death, "poison": run_poison, "ordering": run_ordering}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=[*SCENARIOS, "all"])
    args = parser.parse_args()
    run_id = uuid.uuid4().hex[:6]
    STATE.mkdir(exist_ok=True)
    say(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===  hw8 failure tests, run {run_id}, VERIFY_SEED {config.VERIFY_SEED}, broker {config.BOOTSTRAP}")
    for name in (SCENARIOS if args.scenario == "all" else [args.scenario]):
        outcome = SCENARIOS[name](run_id)
        (RAW / f"failure_{name}.json").write_text(json.dumps({"run_id": run_id, "scenario": name, **outcome}, indent=2))
        say(f"   saved reports/hw08/raw/failure_{name}.json\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
