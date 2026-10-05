import datetime
import secrets

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession, joinedload

from models import Course, Instructor, Session as SessionModel, User

SESSION_TTL_SECONDS = 24 * 60 * 60


# --- passwords 

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# --- users 

def get_user_by_email(db: OrmSession, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def create_user(db: OrmSession, name: str, email: str, password: str) -> User:
    user = User(name=name, email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- sessions 

def create_session(db: OrmSession, user: User) -> SessionModel:
    now = datetime.datetime.utcnow()
    session = SessionModel(
        id=secrets.token_urlsafe(32),
        user_id=user.id,
        created_at=now,
        expires_at=now + datetime.timedelta(seconds=SESSION_TTL_SECONDS),
    )
    db.add(session)
    db.commit()
    return session


def get_valid_session(db: OrmSession, token: str) -> SessionModel | None:
    session = db.get(SessionModel, token)
    if session is None:
        return None
    if datetime.datetime.utcnow() > session.expires_at:
        db.delete(session)
        db.commit()
        return None
    return session


def delete_session(db: OrmSession, token: str) -> None:
    session = db.get(SessionModel, token)
    if session is not None:
        db.delete(session)
        db.commit()


# --- instructors ---------------------------------------------------------

def list_instructors(db: OrmSession, page: int, page_size: int) -> tuple[list[Instructor], int]:
    total = db.scalar(select(func.count()).select_from(Instructor)) or 0
    rows = db.scalars(
        select(Instructor).order_by(Instructor.id).offset((page - 1) * page_size).limit(page_size)
    )
    return list(rows), total


def get_instructor(db: OrmSession, instructor_id: int) -> Instructor | None:
    return db.get(Instructor, instructor_id)


def get_instructor_by_email(db: OrmSession, email: str) -> Instructor | None:
    return db.scalar(select(Instructor).where(Instructor.email == email))


def create_instructor(db: OrmSession, name: str, department: str, email: str) -> Instructor:
    instructor = Instructor(name=name, department=department, email=email)
    db.add(instructor)
    db.commit()
    db.refresh(instructor)
    return instructor


def update_instructor(db: OrmSession, instructor: Instructor, name: str, department: str, email: str) -> Instructor:
    instructor.name = name
    instructor.department = department
    instructor.email = email
    db.commit()
    db.refresh(instructor)
    return instructor


def count_courses_for_instructor(db: OrmSession, instructor_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Course).where(Course.instructor_id == instructor_id)) or 0


def delete_instructor(db: OrmSession, instructor: Instructor) -> None:
    db.delete(instructor)
    db.commit()


# --- courses -------------------------------------------------------------

def list_courses(db: OrmSession, skip: int = 0, limit: int = 100, instructor_id: int | None = None):
    query = select(Course).options(joinedload(Course.instructor)).order_by(Course.id)
    count = select(func.count()).select_from(Course)
    if instructor_id is not None:
        query = query.where(Course.instructor_id == instructor_id)
        count = count.where(Course.instructor_id == instructor_id)
    total = db.scalar(count) or 0
    return list(db.scalars(query.offset(skip).limit(limit))), total


def get_course(db: OrmSession, course_id: int) -> Course | None:
    return db.scalar(select(Course).options(joinedload(Course.instructor)).where(Course.id == course_id))


def get_course_by_code(db: OrmSession, course_code: str) -> Course | None:
    return db.scalar(select(Course).where(Course.course_code == course_code))


def create_course(db: OrmSession, course_title: str, course_code: str, seats_available: int, instructor_id: int) -> Course:
    course = Course(
        course_title=course_title, course_code=course_code, email="", description="", department="",
        seats_available=seats_available, instructor_id=instructor_id,
    )
    db.add(course)
    db.commit()
    return get_course(db, course.id)


def update_course(db: OrmSession, course: Course, course_title: str, course_code: str, seats_available: int, instructor_id: int) -> Course:
    course.course_title = course_title
    course.course_code = course_code
    course.seats_available = seats_available
    course.instructor_id = instructor_id
    db.commit()
    db.expire(course)
    return get_course(db, course.id)


def delete_course(db: OrmSession, course: Course) -> None:
    db.delete(course)
    db.commit()
