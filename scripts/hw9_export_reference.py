#!/usr/bin/env python3
"""HW9 Part 4: export the reference dataset (the ground truth the Evaluator Agent checks answers against) from s8360_rel."""
import json
from pathlib import Path

from sqlalchemy import select

from db import db_session_basede26
from models import Course, Instructor

OUT = Path(__file__).resolve().parent.parent / "part4/reference_data.json"


def main() -> None:
    with db_session_basede26() as session:
        courses = session.execute(select(Course, Instructor.name).join(Instructor, Instructor.id == Course.instructor_id).order_by(Course.id)).all()
        instructors = session.execute(select(Instructor).order_by(Instructor.id)).scalars().all()
    data = {
        "domain": "Campus Course Catalogue and Enrolment (DOMAIN_ID 0)",
        "source": "MySQL s8360_rel, tables courses and instructors",
        "scope": "The catalogue holds only course code, title, department, seats available and instructor. It has no schedule, "
                 "room, tuition, prerequisite, credit, grade or enrolment information.",
        "instructors": [{"name": i.name, "department": i.department} for i in instructors],
        "courses": [{"courseCode": c.course_code, "courseTitle": c.course_title, "department": c.department,
                     "seatsAvailable": c.seats_available, "instructor": name} for c, name in courses],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(OUT.parent.parent)} with {len(data['courses'])} courses and {len(data['instructors'])} instructors")


if __name__ == "__main__":
    main()
