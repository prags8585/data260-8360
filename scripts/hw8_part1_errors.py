#!/usr/bin/env python3
import json
import time

import httpx

from kafka_svc import config
from kafka_svc.bus import new_correlation_id
from kafka_svc.rpc import KafkaRpcClient

COURSE = {"courseTitle": "Cloud Computing", "courseCode": "DATA-270", "seatsAvailable": 40, "instructorId": 1}
API = f"http://127.0.0.1:{config.PORT_BASE}"


def show(label: str, sent_cid: str, reply: dict) -> None:
    kept = reply.get("correlation_id") == sent_cid
    print(f"  {label:42s} success={str(reply.get('success')):5s} correlation_id preserved={kept}  {json.dumps({k: v for k, v in reply.items() if k not in ('correlation_id', 'success')})}")


def main() -> None:
    print(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===  Part 1 error handling through Kafka (client -> {config.REQUEST_TOPIC} -> worker -> {config.RESPONSE_TOPIC})")
    client = KafkaRpcClient("s8360-errors").start()
    created = client.call("CREATE_COURSE", COURSE)
    cases = [
        ("GET_COURSE with an unknown course_id", "GET_COURSE", {"course_id": "00000000-0000-0000-0000-000000000000"}),
        ("unknown operation DELETE_COURSE", "DELETE_COURSE", {"course_id": created["course_id"]}),
        ("CREATE_COURSE with a missing field", "CREATE_COURSE", {k: v for k, v in COURSE.items() if k != "seatsAvailable"}),
        ("CREATE_COURSE with an empty title", "CREATE_COURSE", {**COURSE, "courseTitle": "   "}),
        ("CREATE_COURSE with an invalid course code", "CREATE_COURSE", {**COURSE, "courseCode": "data260"}),
        ("CREATE_COURSE with seatsAvailable=true", "CREATE_COURSE", {**COURSE, "seatsAvailable": True}),
        ("CREATE_COURSE with data that is not an object", "CREATE_COURSE", "just a string"),
    ]
    for label, operation, data in cases:
        cid = new_correlation_id()
        show(label, cid, client.call(operation, data, cid))
    client.close()

    print(f"\n  the same checks through the FastAPI wrapper at {API}")
    for label, method, path, body in (("POST /courses with an invalid code", "post", "/courses", {**COURSE, "courseCode": "x"}),
                                      ("GET /courses/<unknown id>", "get", "/courses/does-not-exist", None)):
        cid = new_correlation_id()
        reply = httpx.request(method, API + path, json=body, headers={"X-Correlation-ID": cid}, timeout=15)
        print(f"  {label:42s} HTTP {reply.status_code} X-Correlation-ID preserved={reply.headers.get('x-correlation-id') == cid}  {reply.text}")


if __name__ == "__main__":
    main()
