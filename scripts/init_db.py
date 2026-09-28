#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import Base, db_session_basede26, engine  # noqa: E402
from models import Course, User  # noqa: E402
import crud  # noqa: E402

DEMO_EMAIL = "karthik.pragada@sjsu.edu"
DEMO_PASSWORD = "data260"
DEMO_NAME = "Karthik Pragada"

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


def main():
    print(f"Creating tables on {engine.url} ...")
    Base.metadata.create_all(bind=engine)
    print("Tables ready: courses, users, sessions")

    db = db_session_basede26()
    try:
        if crud.get_user_by_email(db, DEMO_EMAIL) is None:
            crud.create_user(db, DEMO_NAME, DEMO_EMAIL, DEMO_PASSWORD)
            print(f"Seeded demo user: {DEMO_EMAIL}")
        else:
            print(f"Demo user already exists: {DEMO_EMAIL}")

        existing = {c.course_code for c in db.query(Course).all()}
        added = 0
        for row in SEED_COURSES:
            if row["course_code"] in existing:
                continue
            db.add(Course(**row))
            added += 1
        db.commit()
        print(f"Seeded {added} new course(s); {len(existing) + added} total.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
