#!/usr/bin/env python3


import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import Base, db_session_basede26, engine  # noqa: E402
from models import Course, Instructor  # noqa: E402
from scripts.init_db import COURSE_ASSIGNMENT, seed_instructors  # noqa: E402

FALLBACK_INSTRUCTOR_EMAIL = "priya.nair@campus.example.edu"


def step(msg: str):
    print(f"  - {msg}", flush=True)


def main():
    print(f"HW5 migration on {engine.url}")
    Base.metadata.create_all(bind=engine)  # creates `instructors` if missing
    step("instructors table ready")

    db = db_session_basede26()
    try:
        step(f"seeded {seed_instructors(db)} new instructor(s)")
    finally:
        db.close()

    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("courses")}

    with engine.begin() as conn:
        if "seats_available" not in cols:
            conn.execute(text("ALTER TABLE courses ADD COLUMN seats_available INT NOT NULL DEFAULT 30"))
            step("added courses.seats_available INT NOT NULL DEFAULT 30")
        if "instructor_id" not in cols:
            conn.execute(text("ALTER TABLE courses ADD COLUMN instructor_id INT NULL"))
            step("added courses.instructor_id INT NULL (tightened below)")
        if "created_at" not in cols:
            conn.execute(text("ALTER TABLE courses ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"))
            step("added courses.created_at")
        if "updated_at" not in cols:
            conn.execute(text(
                "ALTER TABLE courses ADD COLUMN updated_at DATETIME NOT NULL "
                "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            ))
            step("added courses.updated_at (ON UPDATE CURRENT_TIMESTAMP)")

    db = db_session_basede26()
    try:
        by_email = {i.email: i.id for i in db.query(Instructor).all()}
        fallback = by_email[FALLBACK_INSTRUCTOR_EMAIL]
        fixed = 0
        for course in db.query(Course).filter(Course.instructor_id.is_(None)).all():
            email, seats = COURSE_ASSIGNMENT.get(course.course_code, (FALLBACK_INSTRUCTOR_EMAIL, 30))
            course.instructor_id = by_email.get(email, fallback)
            course.seats_available = seats
            fixed += 1
        db.commit()
        step(f"back-filled instructor_id on {fixed} existing course(s)")
    finally:
        db.close()

    insp = inspect(engine)
    fk_names = {fk["name"] for fk in insp.get_foreign_keys("courses")}
    unique_cols = [tuple(u["column_names"]) for u in insp.get_unique_constraints("courses")]
    unique_cols += [tuple(i["column_names"]) for i in insp.get_indexes("courses") if i.get("unique")]
    nullable = {c["name"]: c["nullable"] for c in insp.get_columns("courses")}

    with engine.begin() as conn:
        if nullable.get("instructor_id", False):
            conn.execute(text("ALTER TABLE courses MODIFY instructor_id INT NOT NULL"))
            step("courses.instructor_id is now NOT NULL")
        if "fk_courses_instructor" not in fk_names:
            conn.execute(text(
                "ALTER TABLE courses ADD CONSTRAINT fk_courses_instructor "
                "FOREIGN KEY (instructor_id) REFERENCES instructors(id) ON DELETE RESTRICT"
            ))
            step("added FOREIGN KEY fk_courses_instructor ... ON DELETE RESTRICT")
        if ("course_code",) not in unique_cols:
            conn.execute(text("ALTER TABLE courses ADD CONSTRAINT uq_courses_course_code UNIQUE (course_code)"))
            step("added UNIQUE uq_courses_course_code")

    print("Migration complete.")


if __name__ == "__main__":
    main()
