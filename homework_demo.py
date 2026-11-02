#!/usr/bin/env python3
import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

from kafka_svc import config
from kafka_svc.bus import compact, new_correlation_id, setup_logging
from kafka_svc.rpc import KafkaRpcClient

log = logging.getLogger("demo")
COURSE = {"courseTitle": "Cloud Computing", "courseCode": "DATA-270", "seatsAvailable": 40, "instructorId": 1}
API = f"http://127.0.0.1:{config.PORT_BASE}"


class Collector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(self.format(record))


def call_kafka(client: KafkaRpcClient, operation: str, data: dict, correlation_id: str) -> dict:
    return client.call(operation, data, correlation_id)


def call_api(operation: str, data: dict, correlation_id: str) -> dict:
    headers = {"X-Correlation-ID": correlation_id}
    if operation == "CREATE_COURSE":
        log.info("HTTP POST %s/courses correlation_id=%s body=%s", API, correlation_id, compact(data))
        reply = httpx.post(f"{API}/courses", json=data, headers=headers, timeout=15)
    else:
        log.info("HTTP GET %s/courses/%s correlation_id=%s", API, data["course_id"], correlation_id)
        reply = httpx.get(f"{API}/courses/{data['course_id']}", headers=headers, timeout=15)
    log.info("HTTP %d from FastAPI correlation_id=%s body=%s", reply.status_code, correlation_id, compact(reply.json()))
    return reply.json()


def container_lines(names: list[str], since: str, correlation_id: str) -> list[str]:
    lines = []
    for name in names:
        out = subprocess.run(["docker", "logs", "--since", since, name], capture_output=True, text=True).stdout
        out += subprocess.run(["docker", "logs", "--since", since, name], capture_output=True, text=True).stderr
        tag = name.removeprefix("s8360-")
        lines += [f"[{tag}] {line}" for line in out.splitlines() if correlation_id in line]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--via", choices=["kafka", "api"], default="kafka", help="send from the Kafka client directly or through the FastAPI wrapper")
    args = parser.parse_args()

    setup_logging()
    collector = Collector()
    collector.setFormatter(logging.getLogger().handlers[0].formatter)
    logging.getLogger().addHandler(collector)
    since = (datetime.now(timezone.utc) - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    client = KafkaRpcClient(f"{config.PREFIX}-demo").start() if args.via == "kafka" else None
    send = (lambda op, data, cid: call_kafka(client, op, data, cid)) if client else call_api

    correlation_id = new_correlation_id()
    log.info("step 1: created correlation_id=%s (route: %s)", correlation_id, "Kafka client" if client else "FastAPI -> Kafka")
    log.info("step 2: sending CREATE_COURSE to %s (correlation_id=%s)", config.REQUEST_TOPIC, correlation_id)
    created = send("CREATE_COURSE", COURSE, correlation_id)
    course_id = created.get("course_id")
    log.info("step 7: extracted course_id=%s from the CREATE_COURSE response (correlation_id=%s success=%s)", course_id, correlation_id, created.get("success"))
    if not created.get("success"):
        log.error("CREATE_COURSE failed: %s", created)
        return 1

    log.info("step 8: sending GET_COURSE for course_id=%s (correlation_id=%s)", course_id, correlation_id)
    fetched = send("GET_COURSE", {"course_id": course_id}, correlation_id)
    log.info("step 10: retrieved entity correlation_id=%s course=%s", correlation_id, compact(fetched.get("course")))
    preserved = created.get("correlation_id") == correlation_id and fetched.get("correlation_id") == correlation_id
    log.info("step 10: correlation_id preserved end to end: %s (sent %s, CREATE reply %s, GET reply %s)",
             preserved, correlation_id, created.get("correlation_id"), fetched.get("correlation_id"))
    if client:
        client.close()

    time.sleep(0.5)
    names = ["s8360-api", "s8360-worker"] if not client else ["s8360-worker"]
    print("\n=== merged timeline (demo client + container logs, ordered by timestamp, filtered to this correlation_id) ===")
    merged = [(line.split(" ", 1)[0], line) for line in collector.lines if correlation_id in line]
    merged += [(line.split("] ", 1)[1].split(" ", 1)[0], line) for line in container_lines(names, since, correlation_id)]
    for _, line in sorted(merged, key=lambda pair: pair[0]):
        print(line if line.startswith("[") else f"[demo] {line}")
    return 0 if preserved and fetched.get("success") and fetched["course"]["course_id"] == course_id else 1


if __name__ == "__main__":
    sys.exit(main())
