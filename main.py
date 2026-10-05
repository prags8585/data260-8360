
import asyncio
import os

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import api
import auth
import catalog_api
import courses_store as store
import perf_api

app = FastAPI()
app.add_middleware(
    # HW4 Part 1: allows the React dev server (Vite, default port 5173) to
    # call the JSON API in api.py with the session cookie attached. The
    # server-rendered Jinja app doesn't need this -- it's same-origin.
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "s8360-hw3-dev-secret-do-not-use-in-prod"),
    session_cookie="s8360_session",
    max_age=14 * 24 * 60 * 60,
    same_site="lax",
    # Secure by default (real HTTPS deployment). SESSION_HTTPS_ONLY=false is
    # only for taking plain-HTTP UI screenshots locally where TLS tooling
    # can't be used -- the actual secure-cookie behavior is proven over a
    # real HTTPS instance (see reports/hw03/RUN_LOG.txt).
    https_only=os.environ.get("SESSION_HTTPS_ONLY", "true").lower() != "false",
)
app.include_router(auth.router)
app.include_router(api.router)
app.include_router(catalog_api.router)
app.include_router(perf_api.router)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# The Course list itself now lives in courses_store.py, shared with the
# HW4 Part 1 JSON API (api.py) so the Jinja app and the React client read
# and write the same data instead of two separate copies.
COURSES = store.COURSES


def _get_next_id() -> int:
    return store.get_next_id()


def _find_by_id(course_id: int) -> dict | None:
    return store.find_by_id(course_id)


@app.get("/")
def home(request: Request, q: str = "", state: str = "", error: str = ""):
    courses = COURSES
    if state == "empty":
        courses = []
    elif q:
        needle = q.lower()
        courses = [
            c for c in courses
            if needle in c["courseTitle"].lower() or needle in c["courseCode"].lower()
        ]
    course_1 = _find_by_id(1)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "courses": courses, "q": q, "error": error, "course_1": course_1, "state": state,
            "current_user": auth.get_current_user(request),
        },
    )


@app.post("/courses")
async def create_course(
    courseTitle: str = Form(...),
    courseCode: str = Form(...),
    email: str = Form(""),
    description: str = Form(""),
    department: str = Form(""),
    agreeTerms: str | None = Form(None),
):
    if not courseTitle.strip() or not courseCode.strip():
        return RedirectResponse(url="/?error=Course+title+and+code+are+required.", status_code=303)

    await asyncio.sleep(1.5)

    COURSES.append({
        "id": _get_next_id(),
        "courseTitle": courseTitle.strip(),
        "courseCode": courseCode.strip(),
        "email": email.strip(),
        "description": description.strip(),
        "department": department,
        "agreeTerms": bool(agreeTerms),
    })
    return RedirectResponse(url="/", status_code=303)


@app.post("/courses/1/update")
async def update_course_1(courseTitle: str = Form(...), courseCode: str = Form(...)):
    course = _find_by_id(1)
    if course is None:
        return RedirectResponse(url="/?error=Course+with+ID+1+not+found.", status_code=303)
    if not courseTitle.strip() or not courseCode.strip():
        return RedirectResponse(url="/?error=Course+title+and+code+are+required.", status_code=303)

    course["courseTitle"] = courseTitle.strip()
    course["courseCode"] = courseCode.strip()
    return RedirectResponse(url="/", status_code=303)


@app.post("/courses/delete-highest")
async def delete_highest_course():
    if not COURSES:
        return RedirectResponse(url="/?error=No+courses+to+delete.", status_code=303)

    highest = max(COURSES, key=lambda c: c["id"])
    COURSES.remove(highest)
    return RedirectResponse(url="/", status_code=303)
