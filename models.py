

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base

NOW = text("CURRENT_TIMESTAMP")


class Instructor(Base):
    """Related entity (plays the "author" role): one instructor can teach
    many courses. email is the unique field."""

    __tablename__ = "instructors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=NOW)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=NOW, onupdate=func.now()
    )

    courses: Mapped[list["Course"]] = relationship(back_populates="instructor")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "department": self.department,
            "email": self.email,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class Course(Base):
    """Primary domain entity (DOMAIN_ID=0, Campus Course Catalogue).
    course_title is the primary field, course_code the unique field,
    seats_available the numeric field with a default, instructor_id the
    foreign key. ON DELETE RESTRICT: an instructor that still has courses
    cannot be deleted (the API also reports this as a 409)."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_title: Mapped[str] = mapped_column(String(255), nullable=False)
    course_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    department: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    seats_available: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default=text("30"))
    instructor_id: Mapped[int] = mapped_column(
        ForeignKey("instructors.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=NOW)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, server_default=NOW, onupdate=func.now()
    )

    instructor: Mapped["Instructor"] = relationship(back_populates="courses")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "courseTitle": self.course_title,
            "courseCode": self.course_code,
            "email": self.email,
            "description": self.description,
            "department": self.department,
            "seatsAvailable": self.seats_available,
            "instructorId": self.instructor_id,
            "instructorName": self.instructor.name if self.instructor else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
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
