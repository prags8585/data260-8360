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


def gather_facts(question: str) -> dict:
    """Runs the HW5 catalogue tools over the in-memory snapshot and returns only what they returned."""
    departments = course_stats(REPO, "department")["data"]
    instructors = course_stats(REPO, "instructor")["data"]
    courses: list[dict] = []
    for group in departments["groups"]:
        courses += search_courses(REPO, group["group"], 50)["data"]["courses"]
    return {
        "departments": departments["groups"],
        "instructors": instructors["groups"],
        "courses": courses,
        "totals": {"courses": departments["totalCourses"], "seats": departments["totalSeats"]},
        "course_codes": COURSE_CODES,
    }
