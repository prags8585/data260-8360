import hashlib
import logging

import redis
from sqlalchemy import select, update

from cache_svc import config
from db import db_session_basede26
from models import Course, Instructor

log = logging.getLogger("course_db")


class CourseDB:
    """Course rows in MySQL (s8360_rel) with a Redis counter in front of the views column."""

    def __init__(self, session_factory=db_session_basede26, redis_client: redis.Redis | None = None):
        self.session_factory = session_factory
        self.redis_client = redis_client or redis.Redis.from_url(config.REDIS_URL, decode_responses=True)

    # ---- database reads/writes used by the demos -------------------------------------------------------------
    def get_course(self, course_id: int) -> dict | None:
        with self.session_factory() as session:
            row = session.execute(
                select(Course, Instructor.name).join(Instructor, Instructor.id == Course.instructor_id).where(Course.id == course_id)
            ).first()
        if row is None:
            return None
        course, instructor = row
        return {"id": course.id, "courseCode": course.course_code, "courseTitle": course.course_title, "department": course.department,
                "seatsAvailable": course.seats_available, "instructorName": instructor, "views": course.views}

    def set_seats(self, course_code: str, seats: int) -> tuple[int, int]:
        with self.session_factory() as session:
            old = session.execute(select(Course.seats_available).where(Course.course_code == course_code)).scalar_one()
            session.execute(update(Course).where(Course.course_code == course_code).values(seats_available=seats))
            session.commit()
        return old, seats

    def data_version(self, course_codes: list[str] | None = None) -> str:
        """Fingerprint of the answer-relevant columns of the given courses (all courses when none are given).
        The views counter is not part of it, so the Part 1 counter never invalidates a cached answer."""
        query = (select(Course.course_code, Course.course_title, Course.department, Course.seats_available, Instructor.name)
                 .join(Instructor, Instructor.id == Course.instructor_id).order_by(Course.course_code))
        if course_codes:
            query = query.where(Course.course_code.in_(sorted(set(course_codes))))
        with self.session_factory() as session:
            rows = session.execute(query).all()
        return hashlib.md5("|".join(",".join(str(v) for v in row) for row in rows).encode()).hexdigest()[:12]

    # ---- HW9 Part 1: the one new method -----------------------------------------------------------------------
    def increment_course_views(self, course_id: int) -> int:
        key = config.views_key(course_id)
        count = self.redis_client.incr(key)
        if count == 1:
            # the key did not exist (first access or Redis was wiped): resume from the value last synced to MySQL
            with self.session_factory() as session:
                synced = session.execute(select(Course.views).where(Course.id == course_id)).scalar_one_or_none() or 0
            if synced:
                count = self.redis_client.incrby(key, synced)
        if count % config.VIEWS_SYNC_EVERY == 0:
            with self.session_factory() as session:
                session.execute(update(Course).where(Course.id == course_id).values(views=count))
                session.commit()
            log.info("Synced views to database (course_id=%s views=%d)", course_id, count)
        return count
