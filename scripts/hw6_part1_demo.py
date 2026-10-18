#!/usr/bin/env python3


import json
import sys
from pathlib import Path

import requests

BASE = "http://localhost:8260/api/course-docs"
OUT = Path(__file__).resolve().parent.parent / "reports/hw06/raw/part1_api_calls.json"
OUT.parent.mkdir(parents=True, exist_ok=True)
calls = []


def call(label: str, method: str, path: str, expect: int, body=None):
    r = requests.request(method, f"{BASE}{path}", json=body, timeout=15)
    payload = r.json() if r.content else None
    ok = r.status_code == expect
    calls.append({"label": label, "method": method, "path": f"/api/course-docs{path}", "request_body": body,
                  "status": r.status_code, "expected": expect, "pass": ok, "response_body": payload})
    print(f"[{'OK  ' if ok else 'FAIL'}] {method:6} /api/course-docs{path:<28} -> {r.status_code} (expected {expect})  {label}")
    return payload


good = {"title": "Introduction to Distributed Systems", "description": "Consensus, replication and fault tolerance.",
        "category": "Data Science", "start_date": "2027-01-26T09:00:00Z"}

created = call("create (status defaults to 'open')", "POST", "", 201, good)
doc_id = created["id"]
call("create a second document", "POST", "", 201, {"title": "Database Systems", "status": "waitlist",
     "category": "Computer Science", "start_date": "2027-01-27T10:30:00Z"})
call("list all", "GET", "", 200)
call("list filtered (category=Data Science)", "GET", "?category=Data%20Science", 200)
call("get one by id", "GET", f"/{doc_id}", 200)
call("update (PUT) status + title", "PUT", f"/{doc_id}", 200,
     {**good, "title": "Distributed Systems (Updated)", "status": "closed"})

print("--- validation and error handling ---")
call("missing required field (title)", "POST", "", 422, {"category": "Data Science", "start_date": "2027-01-26T09:00:00Z"})
call("invalid enum value (category)", "POST", "", 422, {**good, "category": "Poetry"})
call("invalid enum value (status)", "POST", "", 422, {**good, "status": "archived"})
call("wrong data type (title is a number)", "POST", "", 422, {**good, "title": 12345})
call("incorrect date format", "POST", "", 422, {**good, "start_date": "next tuesday"})
call("title longer than 100 characters", "POST", "", 422, {**good, "title": "x" * 101})
call("unknown extra field rejected", "POST", "", 422, {**good, "credits": 3})
call("unknown id -> not found", "GET", "/6acddcfa5623c47602c60000", 404)
call("malformed id", "GET", "/not-an-object-id", 422)

print("--- delete ---")
call("delete -> 204", "DELETE", f"/{doc_id}", 204)
call("deleted document is gone", "GET", f"/{doc_id}", 404)

OUT.write_text(json.dumps(calls, indent=2))
passed = sum(c["pass"] for c in calls)
print(f"\n{passed}/{len(calls)} Part 1 API checks passed -> {OUT}")
sys.exit(0 if passed == len(calls) else 1)
