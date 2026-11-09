import os

from domain_tools import InMemoryCourseRepo, course_stats, search_courses

CATALOGUE = [
    {"id": 1, "courseCode": "DATA-260", "courseTitle": "Introduction to Distributed Systems", "department": "Data Science", "seatsAvailable": 40, "instructorName": "Dr. Priya Nair"},
    {"id": 2, "courseCode": "DATA-245", "courseTitle": "Machine Learning Foundations", "department": "Data Science", "seatsAvailable": 35, "instructorName": "Dr. Elena Rossi"},
    {"id": 3, "courseCode": "CS-157A", "courseTitle": "Database Systems", "department": "Computer Science", "seatsAvailable": 45, "instructorName": "Dr. Marcus Lee"},
    {"id": 4, "courseCode": "DATA-270", "courseTitle": "Cloud Computing", "department": "Data Science", "seatsAvailable": 30, "instructorName": "Dr. Priya Nair"},
    {"id": 5, "courseCode": "CS-146", "courseTitle": "Data Structures and Algorithms", "department": "Computer Science", "seatsAvailable": 50, "instructorName": "Dr. Marcus Lee"},
    {"id": 6, "courseCode": "STAT-200", "courseTitle": "Applied Statistics", "department": "Statistics", "seatsAvailable": 60, "instructorName": "Dr. Elena Rossi"},
]

REPO = InMemoryCourseRepo(CATALOGUE)
COURSE_CODES = [c["courseCode"] for c in CATALOGUE]


def mysql_courses() -> list[dict]:
    """HW9: the live rows of s8360_rel, so a cached answer can be compared with the record it came from."""
    from sqlalchemy import select

    from db import db_session_basede26
    from models import Course, Instructor

    with db_session_basede26() as session:
        rows = session.execute(select(Course, Instructor.name).join(Instructor, Instructor.id == Course.instructor_id).order_by(Course.id)).all()
    return [{"id": c.id, "courseCode": c.course_code, "courseTitle": c.course_title, "department": c.department,
             "seatsAvailable": c.seats_available, "instructorName": name} for c, name in rows]


def current_courses() -> list[dict]:
    """CATALOGUE_SOURCE=mysql reads s8360_rel on every call; the default is the static snapshot above (HW8 behaviour)."""
    return mysql_courses() if os.environ.get("CATALOGUE_SOURCE", "static") == "mysql" else CATALOGUE


def gather_facts(question: str) -> dict:
    """Runs the HW5 catalogue tools over the catalogue and returns only what they returned."""
    courses_now = current_courses()
    repo = REPO if courses_now is CATALOGUE else InMemoryCourseRepo(courses_now)
    departments = course_stats(repo, "department")["data"]
    instructors = course_stats(repo, "instructor")["data"]
    courses: list[dict] = []
    for group in departments["groups"]:
        courses += search_courses(repo, group["group"], 50)["data"]["courses"]
    return {
        "departments": departments["groups"],
        "instructors": instructors["groups"],
        "courses": courses,
        "totals": {"courses": departments["totalCourses"], "seats": departments["totalSeats"]},
        "course_codes": [c["courseCode"] for c in courses_now],
    }
