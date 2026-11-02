import re
import uuid

OPERATIONS = ("CREATE_COURSE", "GET_COURSE")
COURSE_CODE_PATTERN = re.compile(r"^[A-Z]{2,5}-\d{2,3}[A-Z]?$")
REQUIRED_FIELDS = ("courseTitle", "courseCode", "seatsAvailable", "instructorId")
OPTIONAL_FIELDS = ("department", "description")


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_course(data) -> tuple[dict | None, str | None]:
    """Returns (clean course fields, None) or (None, error message)."""
    if not isinstance(data, dict):
        return None, "data must be a JSON object"
    missing = [f for f in REQUIRED_FIELDS if f not in data or data[f] is None]
    if missing:
        return None, f"Missing required field(s): {', '.join(missing)}"
    unknown = sorted(set(data) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS))
    if unknown:
        return None, f"Unknown field(s): {', '.join(unknown)}"

    title, code = data["courseTitle"], data["courseCode"]
    if not isinstance(title, str) or not title.strip():
        return None, "courseTitle must be a non-empty string"
    if len(title.strip()) > 255:
        return None, "courseTitle must be at most 255 characters"
    if not isinstance(code, str) or not COURSE_CODE_PATTERN.match(code.strip()):
        return None, "courseCode must look like DATA-260 or CS-157A"
    seats, instructor = data["seatsAvailable"], data["instructorId"]
    if not _is_int(seats) or not 0 <= seats <= 1000:
        return None, "seatsAvailable must be an integer between 0 and 1000"
    if not _is_int(instructor) or instructor < 1:
        return None, "instructorId must be a positive integer"

    course = {"courseTitle": title.strip(), "courseCode": code.strip(), "seatsAvailable": seats, "instructorId": instructor}
    for field in OPTIONAL_FIELDS:
        if field in data:
            if not isinstance(data[field], str):
                return None, f"{field} must be a string"
            course[field] = data[field].strip()
    return course, None


def create_course(store: dict, data) -> dict:
    course, error = validate_course(data)
    if error:
        return {"success": False, "error": error}
    course_id = str(uuid.uuid4())
    store[course_id] = {"course_id": course_id, **course}
    return {"success": True, "course_id": course_id, "message": "Course created"}


def get_course(store: dict, data) -> dict:
    course_id = data.get("course_id") if isinstance(data, dict) else None
    if not isinstance(course_id, str) or not course_id.strip():
        return {"success": False, "error": "course_id must be a non-empty string"}
    course = store.get(course_id.strip())
    if course is None:
        return {"success": False, "error": "Course not found"}
    return {"success": True, "course": dict(course)}


def handle_operation(store: dict, operation, data) -> dict:
    if operation == "CREATE_COURSE":
        return create_course(store, data)
    if operation == "GET_COURSE":
        return get_course(store, data)
    return {"success": False, "error": "Unknown operation"}


def handle_request(store: dict, request) -> dict:
    """Always returns a response; correlation_id is echoed whenever the request carried one."""
    if not isinstance(request, dict):
        return {"correlation_id": None, "success": False, "error": "Request must be a JSON object"}
    correlation_id = request.get("correlation_id")
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        return {"correlation_id": None, "success": False, "error": "correlation_id is required"}
    return {"correlation_id": correlation_id, **handle_operation(store, request.get("operation"), request.get("data"))}
