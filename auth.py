"""HW3 Part 1: authentication router for the Course Catalogue app.

Owns login/logout/session-state logic as its own APIRouter so main.py's
home route can stay auth-aware (via get_current_user) without duplicating
this logic. Session storage is Starlette's SessionMiddleware (configured
in main.py); this module only reads/writes request.session.
"""

import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Single hardcoded demo user -- no real user database for this assignment.
DEMO_USERNAME = "instructor"
DEMO_PASSWORD = "data260"

IDLE_TIMEOUT_SECONDS = 60

# Starlette's SessionMiddleware is a pure client-side signed cookie -- the
# server never sees the old cookie again once a new one is issued, so a
# copied pre-logout cookie would otherwise replay successfully forever
# (the signature is still valid; the server just has no memory of
# "logged out"). This server-side epoch closes that gap: any cookie whose
# login_time predates the user's last logout is rejected on sight, even
# though its signature checks out.
_LOGGED_OUT_BEFORE: dict[str, float] = {}


def get_current_user(request: Request) -> str | None:
    """Returns the logged-in username, or None if not logged in, the
    session has been idle past IDLE_TIMEOUT_SECONDS, or this specific
    cookie was issued before the user's most recent logout (a replayed,
    already-logged-out cookie). Either failure clears the session
    server-side on the spot, so the same cookie can't be reused again."""
    user = request.session.get("user")
    if not user:
        return None
    last_seen = request.session.get("last_seen", 0)
    login_time = request.session.get("login_time", 0)
    if time.time() - last_seen > IDLE_TIMEOUT_SECONDS:
        request.session.clear()
        return None
    if login_time <= _LOGGED_OUT_BEFORE.get(user, 0):
        request.session.clear()
        return None
    request.session["last_seen"] = time.time()
    return user


@router.get("/login")
def login_page(request: Request, error: str = ""):
    if get_current_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == DEMO_USERNAME and password == DEMO_PASSWORD:
        now = time.time()
        request.session["user"] = username
        request.session["login_time"] = now
        request.session["last_seen"] = now
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login?error=Invalid+username+or+password.", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login?error=Please+log+in+to+continue.", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})


@router.get("/logout")
def logout(request: Request):
    user = request.session.get("user")
    if user:
        _LOGGED_OUT_BEFORE[user] = time.time()
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
