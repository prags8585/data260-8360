from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

import crud
from db import get_db

router = APIRouter(prefix="/api")

SESSION_COOKIE = "s8360_api_session"


class LoginBody(BaseModel):
    email: str
    password: str


class SignupBody(BaseModel):
    firstName: str
    lastName: str
    email: str
    password: str
    confirmPassword: str


class CourseBody(BaseModel):
    courseTitle: str
    courseCode: str


def require_session(request: Request, db: OrmSession = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Login required")
    session = crud.get_valid_session(db, token)
    if session is None:
        raise HTTPException(status_code=401, detail="Login required")
    return session.user


@router.post("/auth/signup")
def signup(body: SignupBody, response: Response, db: OrmSession = Depends(get_db)):
    first_name = body.firstName.strip()
    last_name = body.lastName.strip()
    email = body.email.strip()

    if not first_name or not last_name or not email or not body.password:
        raise HTTPException(status_code=422, detail="All fields are required")
    if body.password != body.confirmPassword:
        raise HTTPException(status_code=422, detail="Passwords do not match")
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")
    if crud.get_user_by_email(db, email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = crud.create_user(db, f"{first_name} {last_name}", email, body.password)
    session = crud.create_session(db, user)
    response.set_cookie(
        SESSION_COOKIE,
        session.id,
        httponly=True,
        samesite="lax",
        secure=False,  # React dev server talks to the backend over plain HTTP; see README
        max_age=crud.SESSION_TTL_SECONDS,
        path="/",
    )
    return {"email": user.email}


@router.post("/auth/login")
def login(body: LoginBody, response: Response, db: OrmSession = Depends(get_db)):
    user = crud.get_user_by_email(db, body.email)
    if user is None or not crud.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session = crud.create_session(db, user)
    response.set_cookie(
        SESSION_COOKIE,
        session.id,
        httponly=True,
        samesite="lax",
        secure=False,  # React dev server talks to the backend over plain HTTP; see README
        max_age=crud.SESSION_TTL_SECONDS,
        path="/",
    )
    return {"email": user.email}


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: OrmSession = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        crud.delete_session(db, token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user=Depends(require_session)):
    return {"email": user.email}


@router.get("/courses")
def list_courses(db: OrmSession = Depends(get_db), _user=Depends(require_session)):
    return [c.as_dict() for c in crud.list_courses(db)]


@router.get("/courses/{course_id}")
def get_course(course_id: int, db: OrmSession = Depends(get_db), _user=Depends(require_session)):
    course = crud.get_course(db, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course.as_dict()


@router.post("/courses", status_code=201)
def create_course(body: CourseBody, db: OrmSession = Depends(get_db), _user=Depends(require_session)):
    if not body.courseTitle.strip() or not body.courseCode.strip():
        raise HTTPException(status_code=422, detail="courseTitle and courseCode are required")
    course = crud.create_course(db, body.courseTitle.strip(), body.courseCode.strip())
    return course.as_dict()


@router.put("/courses/{course_id}")
def update_course(course_id: int, body: CourseBody, db: OrmSession = Depends(get_db), _user=Depends(require_session)):
    course = crud.get_course(db, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if not body.courseTitle.strip() or not body.courseCode.strip():
        raise HTTPException(status_code=422, detail="courseTitle and courseCode are required")
    course = crud.update_course(db, course, body.courseTitle.strip(), body.courseCode.strip())
    return course.as_dict()


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, db: OrmSession = Depends(get_db), _user=Depends(require_session)):
    course = crud.get_course(db, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    crud.delete_course(db, course)
    return {"ok": True}
