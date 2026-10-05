#!/usr/bin/env python3
"""HW5 Part 1: walks every catalog endpoint (success + each error class)
against the live backend and saves each request/response pair to
reports/hw05/raw/api_demo_calls.json. Cleans up everything it creates.

Requires: backend on PORT_BASE (SESSION_HTTPS_ONLY=false), MySQL up,
scripts/migrate_hw5.py already applied.

Usage: python scripts/hw5_api_demo.py
"""

import json
from pathlib import Path

import requests

BASE = "http://localhost:8260/api"
OUT = Path(__file__).resolve().parent.parent / "reports/hw05/raw/api_demo_calls.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

calls = []
s = requests.Session()


def call(label, method, path, expect, json_body=None, session=None, **kw):
    sess = session or s
    r = sess.request(method, f"{BASE}{path}", json=json_body, **kw)
    try:
        body = r.json() if r.content else None
    except ValueError:
        body = r.text
    ok = r.status_code == expect
    calls.append({
        "label": label, "method": method, "url": f"{BASE}{path}", "request_body": json_body,
        "status": r.status_code, "expected": expect, "pass": ok,
        "x_total_count": r.headers.get("X-Total-Count"), "response_body": body,
    })
    flag = "OK  " if ok else "FAIL"
    print(f"[{flag}] {method:6} {path:45} -> {r.status_code} (expected {expect})  {label}")
    return r


# --- auth -------------------------------------------------------------------
call("no cookie -> unauthorized", "GET", "/instructors", 401, session=requests.Session())
call("login", "POST", "/auth/login", 200, {"email": "karthik.pragada@sjsu.edu", "password": "data260"})

# --- instructors (related entity) -------------------------------------------
r = call("create instructor", "POST", "/instructors", 201,
         {"name": "Dr. Ada Byron", "department": "Computer Science", "email": "ada.byron@campus.example.edu"})
iid = r.json()["id"]
call("list instructors (page 1, size 2)", "GET", "/instructors?page=1&page_size=2", 200)
call("get instructor", "GET", f"/instructors/{iid}", 200)
call("update instructor", "PUT", f"/instructors/{iid}", 200,
     {"name": "Dr. Ada Byron-Lovelace", "department": "Computer Science", "email": "ada.byron@campus.example.edu"})
call("instructor not found", "GET", "/instructors/9999", 404)
call("bad email format -> validation error", "POST", "/instructors", 422,
     {"name": "Dr. Bad Email", "department": "X", "email": "not-an-email"})
call("duplicate email -> constraint violation", "POST", "/instructors", 409,
     {"name": "Dr. Copy", "department": "X", "email": "priya.nair@campus.example.edu"})
call("page_size out of range -> validation error", "GET", "/instructors?page=1&page_size=500", 422)

# --- courses (primary entity) -------------------------------------------------
r = call("create course", "POST", "/courses", 201,
         {"courseTitle": "Cloud Computing", "courseCode": "DATA-270", "seatsAvailable": 25, "instructorId": iid})
cid = r.json()["id"]
call("list courses", "GET", "/courses", 200)
call("get course", "GET", f"/courses/{cid}", 200)
call("update course", "PUT", f"/courses/{cid}", 200,
     {"courseTitle": "Cloud Computing Systems", "courseCode": "DATA-270", "seatsAvailable": 20, "instructorId": iid})
call("course not found", "GET", "/courses/9999", 404)
call("bad course code format -> validation error", "POST", "/courses", 422,
     {"courseTitle": "Bad Code", "courseCode": "data 270", "seatsAvailable": 10, "instructorId": iid})
call("negative seats -> validation error", "POST", "/courses", 422,
     {"courseTitle": "Neg Seats", "courseCode": "DATA-271", "seatsAvailable": -5, "instructorId": iid})
call("duplicate course code -> constraint violation", "POST", "/courses", 409,
     {"courseTitle": "Dup", "courseCode": "DATA-260", "seatsAvailable": 10, "instructorId": iid})
call("unknown instructor -> not found", "POST", "/courses", 404,
     {"courseTitle": "Orphan", "courseCode": "DATA-272", "seatsAvailable": 10, "instructorId": 9999})

# --- relationship query + delete restriction ----------------------------------
call("relationship: courses taught by instructor", "GET", f"/instructors/{iid}/courses", 200)
call("delete instructor that still has courses -> blocked", "DELETE", f"/instructors/{iid}", 409)

# --- cleanup (also demonstrates the successful deletes) -------------------------
call("delete course", "DELETE", f"/courses/{cid}", 204)
call("delete instructor (no courses left)", "DELETE", f"/instructors/{iid}", 204)
call("deleted instructor is gone", "GET", f"/instructors/{iid}", 404)

OUT.write_text(json.dumps(calls, indent=2))
passed = sum(c["pass"] for c in calls)
print(f"\n{passed}/{len(calls)} API checks passed -> {OUT}")
raise SystemExit(0 if passed == len(calls) else 1)
