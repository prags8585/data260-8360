#!/usr/bin/env python3
"""Creates the s8360_rel schema (courses, instructors, users, sessions) and
seeds the demo user, the starter instructors, and the three starter courses.
Idempotent. A database created by HW4 needs scripts/migrate_hw5.py once;
a fresh one gets the HW5 schema from here.

Usage: PYTHONPATH=. python scripts/init_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import Base, db_session_basede26, engine  # noqa: E402
from models import Course, Instructor  # noqa: E402
import crud  # noqa: E402

DEMO_EMAIL = "karthik.pragada@sjsu.edu"
DEMO_PASSWORD = "data260"
DEMO_NAME = "Karthik Pragada"

# Fictional instructors (test data, not real faculty).
SEED_INSTRUCTORS = [
    {"name": "Dr. Priya Nair", "department": "Data Science", "email": "priya.nair@campus.example.edu"},
    {"name": "Dr. Marcus Lee", "department": "Computer Science", "email": "marcus.lee@campus.example.edu"},
    {"name": "Dr. Elena Rossi", "department": "Data Science", "email": "elena.rossi@campus.example.edu"},
    {"name": "Dr. Samuel Okafor", "department": "Engineering", "email": "samuel.okafor@campus.example.edu"},
]

# course_code -> (instructor email, seats_available)
COURSE_ASSIGNMENT = {
    "DATA-260": ("priya.nair@campus.example.edu", 40),
    "DATA-245": ("elena.rossi@campus.example.edu", 35),
    "CS-157A": ("marcus.lee@campus.example.edu", 45),
}

SEED_COURSES = [
    {
        "course_title": "Introduction to Distributed Systems",
        "course_code": "DATA-260",
        "email": "karthik.pragada@sjsu.edu",
        "description": "Consensus, replication, partitioning, and fault tolerance in distributed systems.",
        "department": "Data Science",
    },
    {
        "course_title": "Machine Learning Foundations",
        "course_code": "DATA-245",
        "email": "karthik.pragada@sjsu.edu",
        "description": "Supervised and unsupervised learning, model evaluation, and feature engineering.",
        "department": "Data Science",
    },
    {
        "course_title": "Database Systems",
        "course_code": "CS-157A",
        "email": "karthik.pragada@sjsu.edu",
        "description": "Relational modeling, SQL, transactions, and indexing.",
        "department": "Computer Science",
    },
]


def seed_instructors(db) -> int:
    existing = {i.email for i in db.query(Instructor).all()}
    added = 0
    for row in SEED_INSTRUCTORS:
        if row["email"] not in existing:
            db.add(Instructor(**row))
            added += 1
    db.commit()
    return added


def main():
    print(f"Creating tables on {engine.url} ...")
    Base.metadata.create_all(bind=engine)
    print("Tables ready: instructors, courses, users, sessions")

    db = db_session_basede26()
    try:
        if crud.get_user_by_email(db, DEMO_EMAIL) is None:
            crud.create_user(db, DEMO_NAME, DEMO_EMAIL, DEMO_PASSWORD)
            print(f"Seeded demo user: {DEMO_EMAIL}")
        else:
            print(f"Demo user already exists: {DEMO_EMAIL}")

        print(f"Seeded {seed_instructors(db)} new instructor(s).")

        by_email = {i.email: i for i in db.query(Instructor).all()}
        existing = {c.course_code for c in db.query(Course).all()}
        added = 0
        for row in SEED_COURSES:
            if row["course_code"] in existing:
                continue
            instructor_email, seats = COURSE_ASSIGNMENT[row["course_code"]]
            db.add(Course(**row, instructor_id=by_email[instructor_email].id, seats_available=seats))
            added += 1
        db.commit()
        print(f"Seeded {added} new course(s); {len(existing) + added} total.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
