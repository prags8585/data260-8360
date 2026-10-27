
import datetime
import logging
import os

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

import crud
from db import get_db
from models import User

log = logging.getLogger("jwt_auth")

JWT_SECRET = os.environ.get("JWT_SECRET", "s8360-hw7-dev-signing-key-change-me-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_SECONDS = 30 * 60

# Hash used to keep the response time similar when the username does not exist.
_DUMMY_HASH = crud.hash_password("not-a-real-password")
bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/auth", tags=["auth (JWT)"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=255)


class SignupBody(BaseModel):
    firstName: str = Field(min_length=1, max_length=100)
    lastName: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=255)
    confirmPassword: str


def create_access_token(user: User, ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": user.username,
        "uid": user.id,
        "role": user.role,
        "iat": now,
        "exp": now + datetime.timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: OrmSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Not authenticated: missing bearer token")
    try:
        claims = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token has expired") from None
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token") from None
    user = crud.get_user_by_username(db, claims.get("sub", ""))
    if user is None:
        raise _unauthorized("Token belongs to a user that no longer exists")
    return user


def require_roles(*allowed: str):
    """Dependency factory: valid token required (401), then the role must be in `allowed` (403)."""

    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            log.info("403 for %s (%s): needs one of %s", user.username, user.role, allowed)
            raise HTTPException(status_code=403, detail=f"Role '{user.role}' is not allowed; requires {' or '.join(allowed)}")
        return user

    return dependency


def _token_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_TTL_SECONDS,
        "role": user.role,
    }


@router.post("/login")
def login(body: LoginBody, db: OrmSession = Depends(get_db)):
    user = crud.get_user_by_username(db, body.username)
    password_ok = crud.verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok:
        raise _unauthorized("Invalid username or password")
    return _token_response(user)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "name": user.name, "email": user.email, "role": user.role}


@router.post("/signup", status_code=201)
def signup(body: SignupBody, db: OrmSession = Depends(get_db)):
    """Self-service sign-up always creates a `reader`; roles are changed by a moderator in the database."""
    if body.password != body.confirmPassword:
        raise HTTPException(status_code=422, detail="Passwords do not match")
    email = body.email.strip()
    if crud.get_user_by_email(db, email) is not None or crud.get_user_by_username(db, email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    try:
        user = crud.create_user(db, f"{body.firstName.strip()} {body.lastName.strip()}", email, body.password, username=email, role="reader")
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists") from None
    return _token_response(user)
