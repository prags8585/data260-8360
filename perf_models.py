
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class PerfCourse(Base):
    """Primary domain entity, seeded to 5,000 rows for the N+1 benchmark."""

    __tablename__ = "perf_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_title: Mapped[str] = mapped_column(String(255), nullable=False)
    course_code: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class PerfCourseReview(Base):

    __tablename__ = "perf_course_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(String(255), nullable=False, default="")
