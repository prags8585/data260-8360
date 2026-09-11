"""FastAPI backend for the Course Catalogue app (HW2).

Part 1 scaffold: serves the responsive Jinja2 template with mock in-memory
data so the list/loading/empty/error states can be built and demonstrated
before Part 2 adds real persistence and full CRUD routes.
"""

import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Part 1 placeholder data -- replaced by real storage/CRUD in Part 2.
MOCK_COURSES = [
    {"id": 1, "courseTitle": "Introduction to Distributed Systems", "courseCode": "DATA-260", "department": "Data Science"},
    {"id": 2, "courseTitle": "Machine Learning Foundations", "courseCode": "DATA-245", "department": "Data Science"},
    {"id": 3, "courseTitle": "Database Systems", "courseCode": "CS-157A", "department": "Computer Science"},
]


@app.get("/")
def home(request: Request, q: str = "", state: str = "", error: str = ""):
    courses = MOCK_COURSES
    if state == "empty":
        courses = []
    elif q:
        needle = q.lower()
        courses = [
            c for c in courses
            if needle in c["courseTitle"].lower() or needle in c["courseCode"].lower()
        ]
    return templates.TemplateResponse(
        request,
        "index.html",
        {"courses": courses, "q": q, "error": error},
    )


@app.post("/courses")
async def create_course_stub(request: Request):
    """Part 1 demo stub only: adds a short artificial delay so the loading
    state is genuinely visible, then redirects home without persisting
    anything. Replaced with real create logic in Part 2."""
    await asyncio.sleep(1.5)
    return RedirectResponse(url="/", status_code=303)
