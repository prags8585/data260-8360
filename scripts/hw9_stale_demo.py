#!/usr/bin/env python3
"""HW9 Part 3.5: a cached answer goes stale when its database record changes; the data-version marker catches it."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy import text

from cache_svc.course_db import CourseDB
from db import engine

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports/hw09/raw/stale_demo.json"
QUESTION = "How many seats are available in DATA-260?"
CODE = "DATA-260"


def row() -> str:
    with engine.connect() as connection:
        r = connection.execute(text("SELECT course_code, seats_available FROM courses WHERE course_code = :c"), {"c": CODE}).one()
    return f"courses row {r[0]}: seats_available = {r[1]}"


def show(step: str, r: dict) -> None:
    kind = "HIT " if r["is_cached"] else "MISS"
    print(f"   {kind} similarity={r['similarity']} latency={r['latency_ms']} ms data_version={r['data_version']}"
          + (f" version_check={r['version_check_ms']} ms" if r.get("version_check_ms") is not None else "")
          + (" (stale entry invalidated)" if r.get("stale_invalidated") else ""))
    print(f"   answer: {r['answer']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8260")
    parser.add_argument("--new-seats", type=int, default=12)
    args = parser.parse_args()
    client = httpx.Client(base_url=args.base, timeout=300)
    db = CourseDB()
    original = int(row().split("= ")[1])

    print(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} === 3.5 stale answers and invalidation")
    print(f"cached query: {QUESTION!r} - its answer depends on s8360_rel.courses row {CODE}\n{row()}\n")
    client.delete("/cache")
    print("1. first ask (cache is empty): the agent answers and the answer is stored with the data version of the DATA-260 row")
    first = client.post("/ask", json={"question": QUESTION}).json()
    show("1", first)
    print("\n2. same question again: served from the cache, the version check finds the row unchanged")
    second = client.post("/ask", json={"question": QUESTION}).json()
    show("2", second)

    old, new = db.set_seats(CODE, args.new_seats)
    print(f"\n3. UPDATE courses SET seats_available = {new} WHERE course_code = '{CODE}'   (was {old})\n   {row()}")

    print("\n4. ask again with the version check switched off (what a plain semantic cache does):")
    stale = client.post("/ask", json={"question": QUESTION, "validate_version": False}).json()
    show("4", stale)
    print(f"   -> STALE HIT: the cache says {stale['answer']!r} but the database now says {new} seats")

    print("\n5. ask again with the invalidation strategy on (the stored data version is compared with the current one):")
    fresh = client.post("/ask", json={"question": QUESTION, "validate_version": True}).json()
    show("5", fresh)
    print("\n6. and once more: the new answer is cached under the new data version")
    again = client.post("/ask", json={"question": QUESTION}).json()
    show("6", again)

    db.set_seats(CODE, original)
    client.delete("/cache")
    print(f"\ncleanup: restored seats_available to {original}; {row()}; cache flushed")
    ok = stale["is_cached"] and str(old) in stale["answer"] and not fresh["is_cached"] and fresh["stale_invalidated"] and str(new) in fresh["answer"] \
        and again["is_cached"] and str(new) in again["answer"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"question": QUESTION, "course": CODE, "seats_before": old, "seats_after": new, "first": first, "second": second,
                               "stale_hit": stale, "after_invalidation": fresh, "cached_again": again, "ok": bool(ok)}, indent=2))
    print("RESULT: stale hit shown, invalidation corrected it" if ok else "RESULT: unexpected outcome")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
