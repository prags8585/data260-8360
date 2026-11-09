#!/usr/bin/env python3
"""HW9 Part 1: Redis view counter for the Course entity, synced to MySQL every 10 increments."""
import argparse
import logging
import sys

from sqlalchemy import text

from cache_svc import config
from cache_svc.course_db import CourseDB
from db import engine


class Tick(logging.Handler):
    """Collects the 'Synced views to database' log lines so they print right after the access line that caused them."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append("\u2713 " + record.getMessage().split(" (")[0])

    def flush_lines(self) -> None:
        while self.lines:
            print(self.lines.pop(0))


def db_views(course_id: int) -> int:
    with engine.connect() as connection:
        return connection.execute(text("SELECT views FROM courses WHERE id = :i"), {"i": course_id}).scalar_one()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-id", type=int, default=1)
    parser.add_argument("--accesses", type=int, default=25)
    args = parser.parse_args()

    db = CourseDB()
    tick = Tick()
    logging.getLogger("course_db").addHandler(tick)
    logging.getLogger("course_db").setLevel(logging.INFO)
    key = config.views_key(args.course_id)
    course = db.get_course(args.course_id)
    db.redis_client.delete(key)
    with engine.begin() as connection:
        connection.execute(text("UPDATE courses SET views = 0 WHERE id = :i"), {"i": args.course_id})

    print(f"Entity: course {course['courseCode']} (course_id={args.course_id}), Redis key {key}\n")
    print("=== Testing Counter ===\n")
    for i in range(1, args.accesses + 1):
        total = db.increment_course_views(args.course_id)
        print(f"Access #{i}: Total = {total}")
        tick.flush_lines()
        if total != i:
            print(f"  !! expected {i}")
            return 1

    redis_value = int(db.redis_client.get(key))
    print(f"\nafter {args.accesses} accesses: Redis {key} = {redis_value}, MySQL courses.views = {db_views(args.course_id)}"
          f" (last sync at {args.accesses - args.accesses % config.VIEWS_SYNC_EVERY})")

    print("\n=== Redis key lost: the counter resumes from the value synced to MySQL ===")
    db.redis_client.delete(key)
    print(f"deleted {key} from Redis; MySQL courses.views = {db_views(args.course_id)}")
    total = db.increment_course_views(args.course_id)
    print(f"Access #{args.accesses + 1}: Total = {total}")
    tick.flush_lines()
    ok = total == args.accesses - args.accesses % config.VIEWS_SYNC_EVERY + 1
    print("resumed from the synced value" if ok else "!! did not resume")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
