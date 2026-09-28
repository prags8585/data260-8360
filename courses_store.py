COURSES: list[dict] = [
    {
        "id": 1,
        "courseTitle": "Introduction to Distributed Systems",
        "courseCode": "DATA-260",
        "email": "karthik.pragada@sjsu.edu",
        "description": "Consensus, replication, partitioning, and fault tolerance in distributed systems.",
        "department": "Data Science",
    },
    {
        "id": 2,
        "courseTitle": "Machine Learning Foundations",
        "courseCode": "DATA-245",
        "email": "karthik.pragada@sjsu.edu",
        "description": "Supervised and unsupervised learning, model evaluation, and feature engineering.",
        "department": "Data Science",
    },
    {
        "id": 3,
        "courseTitle": "Database Systems",
        "courseCode": "CS-157A",
        "email": "karthik.pragada@sjsu.edu",
        "description": "Relational modeling, SQL, transactions, and indexing.",
        "department": "Computer Science",
    },
]
_next_id = 4


def get_next_id() -> int:
    global _next_id
    course_id = _next_id
    _next_id += 1
    return course_id


def find_by_id(course_id: int) -> dict | None:
    return next((c for c in COURSES if c["id"] == course_id), None)
