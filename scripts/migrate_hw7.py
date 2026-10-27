#!/usr/bin/env python3

import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import crud  # noqa: E402
from db import Base, db_session_basede26, engine  # noqa: E402
from models import Course, Instructor  # noqa: E402

DEMO_ACCOUNTS = [
    # username, display name, email, password, role
    ("reader1", "Riya Reader", "reader1@campus.example.edu", "Reader#Pass2026", "reader"),
    ("writer1", "Wes Writer", "writer1@campus.example.edu", "Writer#Pass2026", "writer"),
    ("moderator1", "Mona Moderator", "moderator1@campus.example.edu", "Moderator#Pass2026", "moderator"),
]
OWNER_EMAIL = "karthik.pragada@sjsu.edu"  # existing HW4 account becomes a moderator
EXTRA_COURSES = [
    # code, title, department, seats, instructor email
    ("DATA-230", "Data Visualization", "Data Science", 30, "samuel.okafor@campus.example.edu"),
    ("CS-146", "Web Programming", "Computer Science", 50, "marcus.lee@campus.example.edu"),
    ("ENGR-200", "Engineering Analytics", "Engineering", 25, "samuel.okafor@campus.example.edu"),
]


def step(msg: str) -> None:
    print(f"  - {msg}", flush=True)


def add_columns() -> None:
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    with engine.begin() as conn:
        if "username" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(64) NULL"))
            conn.execute(text("UPDATE users SET username = SUBSTRING_INDEX(email, '@', 1) WHERE username IS NULL"))
            conn.execute(text("ALTER TABLE users MODIFY username VARCHAR(64) NOT NULL"))
            conn.execute(text("ALTER TABLE users ADD CONSTRAINT uq_users_username UNIQUE (username)"))
            step("added users.username (back-filled from the e-mail local part, NOT NULL, UNIQUE)")
        if "role" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN role ENUM('reader','writer','moderator') NOT NULL DEFAULT 'reader'"))
            step("added users.role ENUM('reader','writer','moderator') DEFAULT 'reader'")


def seed_users(db) -> None:
    for username, name, email, password, role in DEMO_ACCOUNTS:
        if crud.get_user_by_username(db, username) is None:
            crud.create_user(db, name, email, password, username=username, role=role)
            step(f"created demo user {username} ({role}) with a bcrypt password hash")
    owner = crud.get_user_by_email(db, OWNER_EMAIL)
    if owner is not None and owner.role != "moderator":
        owner.role = "moderator"
        db.commit()
        step(f"{OWNER_EMAIL} promoted to moderator")


def seed_courses(db) -> None:
    from sqlalchemy import select

    added = 0
    for code, title, dept, seats, instructor_email in EXTRA_COURSES:
        if db.scalar(select(Course).where(Course.course_code == code)) is None:
            instructor = db.scalar(select(Instructor).where(Instructor.email == instructor_email))
            db.add(Course(course_title=title, course_code=code, department=dept, seats_available=seats, instructor_id=instructor.id))
            added += 1
    db.commit()
    step(f"seeded {added} extra course(s)")


def main() -> None:
    print(f"HW7 migration on {engine.url}")
    Base.metadata.create_all(bind=engine)
    add_columns()
    db = db_session_basede26()
    try:
        seed_users(db)
        seed_courses(db)
    finally:
        db.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
