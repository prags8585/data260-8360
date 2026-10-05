"""Pydantic request/response schemas for the HW5 catalog API.

The unique fields have validated formats:
  - instructor email   -> local@domain.tld
  - course code        -> 2-5 capital letters, a dash, 2-3 digits, optional
                          capital letter suffix (DATA-260, CS-157A)
"""

from pydantic import BaseModel, ConfigDict, Field

EMAIL_PATTERN = r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
COURSE_CODE_PATTERN = r"^[A-Z]{2,5}-\d{2,3}[A-Z]?$"


class InstructorIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255, examples=["Dr. Ada Byron"])
    department: str = Field(default="", max_length=128, examples=["Computer Science"])
    email: str = Field(max_length=255, pattern=EMAIL_PATTERN, examples=["ada.byron@campus.example.edu"])


class InstructorOut(BaseModel):
    id: int
    name: str
    department: str
    email: str
    createdAt: str | None = None
    updatedAt: str | None = None


class InstructorPage(BaseModel):
    items: list[InstructorOut]
    total: int
    page: int
    pageSize: int
    pages: int


class CourseIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    courseTitle: str = Field(min_length=1, max_length=255, examples=["Cloud Computing"])
    courseCode: str = Field(pattern=COURSE_CODE_PATTERN, max_length=64, examples=["DATA-270"])
    seatsAvailable: int = Field(default=30, ge=0, le=1000)
    instructorId: int = Field(ge=1)


class CourseOut(BaseModel):
    id: int
    courseTitle: str
    courseCode: str
    email: str = ""
    description: str = ""
    department: str = ""
    seatsAvailable: int
    instructorId: int
    instructorName: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
