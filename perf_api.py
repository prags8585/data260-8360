import threading
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import event
from sqlalchemy.orm import Session as OrmSession
from fastapi import Depends

from db import engine, get_db
from perf_models import PerfCourse, PerfCourseReview

router = APIRouter(prefix="/api/perf")

_local = threading.local()


def _count_listener(conn, cursor, statement, parameters, context, executemany):
    if getattr(_local, "counting", False):
        _local.count = getattr(_local, "count", 0) + 1


event.listen(engine, "before_cursor_execute", _count_listener)


class QueryCounter:
    def __enter__(self):
        _local.counting = True
        _local.count = 0
        return self

    def __exit__(self, *exc):
        _local.counting = False

    @property
    def count(self) -> int:
        return getattr(_local, "count", 0)


@router.get("/courses")
def perf_courses(
    response: Response,
    page: int = 1,
    page_size: int = 10,
    mode: str = "naive",
    db: OrmSession = Depends(get_db),
):
    if mode not in ("naive", "fixed"):
        raise HTTPException(status_code=422, detail="mode must be 'naive' or 'fixed'")
    if page_size not in (10, 50, 200):
        raise HTTPException(status_code=422, detail="page_size must be 10, 50, or 200 for this benchmark")

    with QueryCounter() as qc:
        offset = (page - 1) * page_size
        courses = (
            db.query(PerfCourse)
            .order_by(PerfCourse.id)
            .offset(offset)
            .limit(page_size)
            .all()
        )

        if mode == "naive":
            results = []
            for c in courses:
                reviews = (
                    db.query(PerfCourseReview)
                    .filter(PerfCourseReview.course_id == c.id)
                    .all()
                )
                results.append({
                    "id": c.id, "courseTitle": c.course_title, "courseCode": c.course_code,
                    "department": c.department,
                    "reviews": [{"rating": r.rating, "comment": r.comment} for r in reviews],
                })
        else:  # fixed: eager-load with a single IN query instead of one-per-row
            ids = [c.id for c in courses]
            reviews_by_course = defaultdict(list)
            if ids:
                for r in db.query(PerfCourseReview).filter(PerfCourseReview.course_id.in_(ids)).all():
                    reviews_by_course[r.course_id].append(r)
            results = [{
                "id": c.id, "courseTitle": c.course_title, "courseCode": c.course_code,
                "department": c.department,
                "reviews": [{"rating": r.rating, "comment": r.comment} for r in reviews_by_course[c.id]],
            } for c in courses]

    response.headers["X-SQL-Query-Count"] = str(qc.count)
    return {"page": page, "page_size": page_size, "mode": mode, "count": len(results), "results": results}


@router.get("/meta")
def perf_meta(db: OrmSession = Depends(get_db)):
    return {
        "total_courses": db.query(PerfCourse).count(),
        "total_reviews": db.query(PerfCourseReview).count(),
    }
