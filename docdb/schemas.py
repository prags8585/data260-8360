from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CourseStatus(str, Enum):
    open = "open"
    waitlist = "waitlist"
    closed = "closed"


class CourseCategory(str, Enum):
    computer_science = "Computer Science"
    data_science = "Data Science"
    business = "Business"
    engineering = "Engineering"


class CourseDocIn(BaseModel):
    """Body for POST and PUT. Unknown fields are rejected (422)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(min_length=1, max_length=100, examples=["Introduction to Distributed Systems"])
    description: str | None = Field(default=None, max_length=1000)
    status: CourseStatus = CourseStatus.open
    category: CourseCategory
    start_date: datetime = Field(examples=["2026-01-26T09:00:00Z"])


class CourseDocOut(BaseModel):
    id: str
    title: str
    description: str | None = None
    status: CourseStatus
    category: CourseCategory
    start_date: datetime
    created_at: datetime
    updated_at: datetime
