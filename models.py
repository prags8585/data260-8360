import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class Course(Base):
    """Primary domain entity (DOMAIN_ID=0, Campus Course Catalogue).
    course_title is the primary field, course_code the secondary field
    (matches DOMAIN_SCHEMA.md); the rest carries over the extra fields the
    HW1/2 form already collected."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_title: Mapped[str] = mapped_column(String(255), nullable=False)
    course_code: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    department: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "courseTitle": self.course_title,
            "courseCode": self.course_code,
            "email": self.email,
            "description": self.description,
            "department": self.department,
        }


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")


class Session(Base):
    """id is the opaque session token itself -- the only thing the
    browser's HTTP-only cookie holds. No user data goes in the cookie."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped["User"] = relationship(back_populates="sessions")
