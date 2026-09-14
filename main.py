"""FastAPI backend for the Course Catalogue app (HW2 Part 2).

Real in-memory CRUD for the Course entity: create, update record #1,
delete the highest-ID record, and search by primary/secondary field.
Server-rendered (Jinja2), Post/Redirect/Get throughout.
"""

import asyncio

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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


def _get_next_id() -> int:
    global _next_id
    course_id = _next_id
    _next_id += 1
    return course_id


def _find_by_id(course_id: int) -> dict | None:
    return next((c for c in COURSES if c["id"] == course_id), None)


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
        {"courses": courses, "q": q, "error": error, "course_1": course_1, "state": state},
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
