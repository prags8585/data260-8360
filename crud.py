import datetime
import secrets

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from models import Course, Session as SessionModel, User

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


# --- courses 

def list_courses(db: OrmSession) -> list[Course]:
    return list(db.scalars(select(Course).order_by(Course.id)))


def get_course(db: OrmSession, course_id: int) -> Course | None:
    return db.get(Course, course_id)


def create_course(db: OrmSession, course_title: str, course_code: str) -> Course:
    course = Course(course_title=course_title, course_code=course_code, email="", description="", department="")
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def update_course(db: OrmSession, course: Course, course_title: str, course_code: str) -> Course:
    course.course_title = course_title
    course.course_code = course_code
    db.commit()
    db.refresh(course)
    return course


def delete_course(db: OrmSession, course: Course) -> None:
    db.delete(course)
    db.commit()
