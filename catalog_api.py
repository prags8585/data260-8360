

import math

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

import crud
from api import require_session
from db import get_db
from schemas import CourseIn, CourseOut, InstructorIn, InstructorOut, InstructorPage

router = APIRouter(prefix="/api", dependencies=[Depends(require_session)])


def _instructor_or_404(db: OrmSession, instructor_id: int):
    instructor = crud.get_instructor(db, instructor_id)
    if instructor is None:
        raise HTTPException(status_code=404, detail=f"Instructor {instructor_id} not found")
    return instructor


def _course_or_404(db: OrmSession, course_id: int):
    course = crud.get_course(db, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"Course {course_id} not found")
    return course


# --- Instructors (related entity) ---------------------------------------

@router.post("/instructors", response_model=InstructorOut, status_code=201)
def create_instructor(body: InstructorIn, db: OrmSession = Depends(get_db)):
    if crud.get_instructor_by_email(db, body.email):
        raise HTTPException(status_code=409, detail=f"An instructor with email {body.email} already exists")
    try:
        return crud.create_instructor(db, body.name, body.department, body.email).as_dict()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Instructor violates a database constraint")


@router.get("/instructors", response_model=InstructorPage)
def list_instructors(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(10, ge=1, le=100, description="items per page (max 100)"),
    db: OrmSession = Depends(get_db),
):
    rows, total = crud.list_instructors(db, page, page_size)
    return {
        "items": [r.as_dict() for r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "pages": math.ceil(total / page_size) if total else 0,
    }


@router.get("/instructors/{instructor_id}", response_model=InstructorOut)
def get_instructor(instructor_id: int, db: OrmSession = Depends(get_db)):
    return _instructor_or_404(db, instructor_id).as_dict()


@router.put("/instructors/{instructor_id}", response_model=InstructorOut)
def update_instructor(instructor_id: int, body: InstructorIn, db: OrmSession = Depends(get_db)):
    instructor = _instructor_or_404(db, instructor_id)
    existing = crud.get_instructor_by_email(db, body.email)
    if existing is not None and existing.id != instructor_id:
        raise HTTPException(status_code=409, detail=f"An instructor with email {body.email} already exists")
    try:
        return crud.update_instructor(db, instructor, body.name, body.department, body.email).as_dict()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Instructor violates a database constraint")


@router.delete("/instructors/{instructor_id}", status_code=204)
def delete_instructor(instructor_id: int, db: OrmSession = Depends(get_db)):
    instructor = _instructor_or_404(db, instructor_id)
    n = crud.count_courses_for_instructor(db, instructor_id)
    if n:
        # Deliberate behaviour (documented): no cascade. The FK is also ON DELETE RESTRICT in MySQL.
        raise HTTPException(
            status_code=409,
            detail=f"Instructor {instructor_id} still has {n} course(s); reassign or delete them first",
        )
    try:
        crud.delete_instructor(db, instructor)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Instructor is still referenced by other records")
    return Response(status_code=204)


@router.get("/instructors/{instructor_id}/courses", response_model=list[CourseOut])
def courses_for_instructor(instructor_id: int, response: Response, db: OrmSession = Depends(get_db)):
    """The relationship query: every course taught by one instructor."""
    _instructor_or_404(db, instructor_id)
    rows, total = crud.list_courses(db, 0, 1000, instructor_id=instructor_id)
    response.headers["X-Total-Count"] = str(total)
    return [r.as_dict() for r in rows]


# --- Courses (primary entity) --------------------------------------------

def _check_instructor_exists(db: OrmSession, instructor_id: int):
    if crud.get_instructor(db, instructor_id) is None:
        raise HTTPException(status_code=404, detail=f"Instructor {instructor_id} not found")


@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(body: CourseIn, db: OrmSession = Depends(get_db)):
    _check_instructor_exists(db, body.instructorId)
    if crud.get_course_by_code(db, body.courseCode):
        raise HTTPException(status_code=409, detail=f"A course with code {body.courseCode} already exists")
    try:
        course = crud.create_course(db, body.courseTitle, body.courseCode, body.seatsAvailable, body.instructorId)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Course violates a database constraint")
    return course.as_dict()


@router.get("/courses", response_model=list[CourseOut])
def list_courses(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    instructor_id: int | None = Query(None, ge=1),
    db: OrmSession = Depends(get_db),
):
    rows, total = crud.list_courses(db, skip, limit, instructor_id)
    response.headers["X-Total-Count"] = str(total)
    return [r.as_dict() for r in rows]


@router.get("/courses/{course_id}", response_model=CourseOut)
def get_course(course_id: int, db: OrmSession = Depends(get_db)):
    return _course_or_404(db, course_id).as_dict()


@router.put("/courses/{course_id}", response_model=CourseOut)
def update_course(course_id: int, body: CourseIn, db: OrmSession = Depends(get_db)):
    course = _course_or_404(db, course_id)
    _check_instructor_exists(db, body.instructorId)
    clash = crud.get_course_by_code(db, body.courseCode)
    if clash is not None and clash.id != course_id:
        raise HTTPException(status_code=409, detail=f"A course with code {body.courseCode} already exists")
    try:
        updated = crud.update_course(db, course, body.courseTitle, body.courseCode, body.seatsAvailable, body.instructorId)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Course violates a database constraint")
    return updated.as_dict()


@router.delete("/courses/{course_id}", status_code=204)
def delete_course(course_id: int, db: OrmSession = Depends(get_db)):
    course = _course_or_404(db, course_id)
    crud.delete_course(db, course)
    return Response(status_code=204)
