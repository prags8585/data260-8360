

import logging
import sys
from typing import Any, Protocol

from resilience import INTERACTIVE, RetriesExhausted, RetryPolicy, call_with_retry

SEARCH_LIMIT_MIN, SEARCH_LIMIT_MAX = 1, 50
MAX_QUERY_LENGTH = 100
GROUP_BY_CHOICES = ("department", "instructor")


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(stream=sys.stderr, level=level, format="%(asctime)s %(name)s %(levelname)s %(message)s", force=True)


log = logging.getLogger("domain_tools")


# --- response envelope --------------------------------------------------------

def ok(data: Any) -> dict:
    return {"ok": True, "data": data, "error": None}


def fail(error: str) -> dict:
    return {"ok": False, "data": None, "error": error}


# --- repositories (dependency injection point) ------------------------------------

class CourseRepo(Protocol):
    def search(self, query: str, limit: int) -> list[dict]: ...
    def get(self, course_id: int) -> dict | None: ...
    def stats(self, group_by: str) -> list[dict]: ...


class SqlCourseRepo:
    """The real MySQL-backed repository (db_session_basede26 from db.py)."""

    def _session(self):
        from db import db_session_basede26
        return db_session_basede26()

    @staticmethod
    def _card(c) -> dict:
        return {
            "id": c.id, "courseCode": c.course_code, "courseTitle": c.course_title,
            "department": c.department, "seatsAvailable": c.seats_available,
            "instructorName": c.instructor.name if c.instructor else None,
        }

    def search(self, query: str, limit: int) -> list[dict]:
        from sqlalchemy import or_, select
        from sqlalchemy.orm import joinedload
        from models import Course

        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        db = self._session()
        try:
            rows = db.scalars(
                select(Course).options(joinedload(Course.instructor))
                .where(or_(Course.course_title.ilike(pattern, escape="\\"),
                           Course.course_code.ilike(pattern, escape="\\"),
                           Course.department.ilike(pattern, escape="\\")))
                .order_by(Course.id).limit(limit)
            )
            return [self._card(c) for c in rows]
        finally:
            db.close()

    def get(self, course_id: int) -> dict | None:
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload
        from models import Course

        db = self._session()
        try:
            c = db.scalar(select(Course).options(joinedload(Course.instructor)).where(Course.id == course_id))
            if c is None:
                return None
            card = self._card(c)
            card.update({
                "description": c.description,
                "instructor": {"name": c.instructor.name, "department": c.instructor.department} if c.instructor else None,
            })
            return card
        finally:
            db.close()

    def stats(self, group_by: str) -> list[dict]:
        from sqlalchemy import func, select
        from models import Course, Instructor

        db = self._session()
        try:
            if group_by == "department":
                key = Course.department
                query = select(key, func.count(Course.id), func.coalesce(func.sum(Course.seats_available), 0)).group_by(key).order_by(key)
            else:
                key = Instructor.name
                query = (select(key, func.count(Course.id), func.coalesce(func.sum(Course.seats_available), 0))
                         .join(Course, Course.instructor_id == Instructor.id).group_by(key).order_by(key))
            return [{"group": g, "courses": int(n), "totalSeats": int(s)} for g, n, s in db.execute(query)]
        finally:
            db.close()


class InMemoryCourseRepo:
    """Fixture repository for offline tests: no database, no network."""

    def __init__(self, courses: list[dict]):
        self._courses = courses

    def search(self, query: str, limit: int) -> list[dict]:
        q = query.lower()
        hits = [c for c in self._courses
                if q in c["courseTitle"].lower() or q in c["courseCode"].lower() or q in c["department"].lower()]
        return [self._card(c) for c in hits[:limit]]

    @staticmethod
    def _card(c: dict) -> dict:
        keys = ("id", "courseCode", "courseTitle", "department", "seatsAvailable", "instructorName")
        return {k: c[k] for k in keys}

    def get(self, course_id: int) -> dict | None:
        for c in self._courses:
            if c["id"] == course_id:
                card = self._card(c)
                card.update({"description": c.get("description", ""), "instructor": {"name": c["instructorName"], "department": c["department"]}})
                return card
        return None

    def stats(self, group_by: str) -> list[dict]:
        key = "department" if group_by == "department" else "instructorName"
        groups: dict[str, dict] = {}
        for c in self._courses:
            g = groups.setdefault(c[key], {"group": c[key], "courses": 0, "totalSeats": 0})
            g["courses"] += 1
            g["totalSeats"] += c["seatsAvailable"]
        return sorted(groups.values(), key=lambda g: g["group"])


class ResilientRepo:
    """Wraps any CourseRepo so every storage call gets a timeout and a
    bounded exponential-backoff retry (Part 3). Exhausted retries raise
    RetriesExhausted, which the tools below turn into an error envelope."""

    def __init__(self, inner: CourseRepo, policy: RetryPolicy = INTERACTIVE, sleep=None, trace=None):
        self.inner, self.policy, self.trace = inner, policy, trace
        self._sleep = sleep

    def _call(self, fn):
        kwargs = {"trace": self.trace}
        if self._sleep is not None:
            kwargs["sleep"] = self._sleep
        return call_with_retry(fn, self.policy, **kwargs)

    def search(self, query, limit):
        return self._call(lambda: self.inner.search(query, limit))

    def get(self, course_id):
        return self._call(lambda: self.inner.get(course_id))

    def stats(self, group_by):
        return self._call(lambda: self.inner.stats(group_by))


def default_repo() -> CourseRepo:
    return ResilientRepo(SqlCourseRepo(), INTERACTIVE)


# --- the three tools ------------------------------------------------------------------

def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _storage_error(exc: Exception) -> dict:
    if isinstance(exc, RetriesExhausted):
        log.error("storage unavailable: %s", exc)
        return fail(f"storage unavailable after {exc.attempts} attempts: {exc.errors[-1]}")
    log.exception("unexpected storage error")
    return fail(f"storage error: {type(exc).__name__}: {exc}")


def search_courses(repo: CourseRepo, query: Any, limit: Any = 10) -> dict:
    """Search courses by title, code or department (case-insensitive substring)."""
    if not isinstance(query, str) or not query.strip():
        return fail("query must be a non-empty string")
    if len(query.strip()) > MAX_QUERY_LENGTH:
        return fail(f"query must be at most {MAX_QUERY_LENGTH} characters")
    if not _is_int(limit) or not SEARCH_LIMIT_MIN <= limit <= SEARCH_LIMIT_MAX:
        return fail(f"limit must be an integer between {SEARCH_LIMIT_MIN} and {SEARCH_LIMIT_MAX}")
    try:
        rows = repo.search(query.strip(), limit)
    except Exception as exc:
        return _storage_error(exc)
    return ok({"count": len(rows), "courses": rows})


def course_detail(repo: CourseRepo, course_id: Any) -> dict:
    """Full detail for one course, including its instructor."""
    if not _is_int(course_id) or course_id < 1:
        return fail("course_id must be a positive integer")
    try:
        row = repo.get(course_id)
    except Exception as exc:
        return _storage_error(exc)
    if row is None:
        return fail(f"course {course_id} not found")
    return ok(row)


def course_stats(repo: CourseRepo, group_by: Any = "department") -> dict:
    """Aggregate: course count and total available seats per department or per instructor."""
    if group_by not in GROUP_BY_CHOICES:
        return fail(f"group_by must be one of: {', '.join(GROUP_BY_CHOICES)}")
    try:
        groups = repo.stats(group_by)
    except Exception as exc:
        return _storage_error(exc)
    return ok({
        "group_by": group_by, "groups": groups,
        "totalCourses": sum(g["courses"] for g in groups),
        "totalSeats": sum(g["totalSeats"] for g in groups),
    })


TOOLS = {"search_courses": search_courses, "course_detail": course_detail, "course_stats": course_stats}
