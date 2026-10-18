import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Response
from pymongo import ReturnDocument
from pymongo.errors import WriteError

from docdb import config
from docdb.mongo import get_db
from docdb.schemas import CourseCategory, CourseDocIn, CourseDocOut, CourseStatus

log = logging.getLogger("docdb.routes")
router = APIRouter(prefix="/api/course-docs", tags=["course documents (MongoDB)"])


def _col():
    return get_db()[config.COURSE_COLLECTION]


def _oid(doc_id: str) -> ObjectId:
    if not ObjectId.is_valid(doc_id):
        raise HTTPException(status_code=422, detail=f"'{doc_id}' is not a valid document id (expected 24 hex characters)")
    return ObjectId(doc_id)


def _out(doc: dict) -> CourseDocOut:
    return CourseDocOut(
        id=str(doc["_id"]), title=doc["title"], description=doc.get("description"), status=doc["status"],
        category=doc["category"], start_date=doc["start_date"], created_at=doc["created_at"], updated_at=doc["updated_at"],
    )


def _payload(body: CourseDocIn) -> dict:
    return {
        "title": body.title, "description": body.description, "status": body.status.value,
        "category": body.category.value, "start_date": body.start_date,
    }


@router.post("", response_model=CourseDocOut, status_code=201)
def create_doc(body: CourseDocIn):
    now = datetime.now(timezone.utc)
    doc = {**_payload(body), "created_at": now, "updated_at": now}
    try:
        doc["_id"] = _col().insert_one(doc).inserted_id
    except WriteError as exc:
        raise HTTPException(status_code=422, detail=f"database validation failed: {exc.details.get('errmsg', exc)}")
    return _out(doc)


@router.get("", response_model=list[CourseDocOut])
def list_docs(
    response: Response,
    status: CourseStatus | None = None,
    category: CourseCategory | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    query = {}
    if status:
        query["status"] = status.value
    if category:
        query["category"] = category.value
    response.headers["X-Total-Count"] = str(_col().count_documents(query))
    return [_out(d) for d in _col().find(query).sort("_id", 1).skip(skip).limit(limit)]


@router.get("/{doc_id}", response_model=CourseDocOut)
def get_doc(doc_id: str):
    doc = _col().find_one({"_id": _oid(doc_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Course document {doc_id} not found")
    return _out(doc)


@router.put("/{doc_id}", response_model=CourseDocOut)
def update_doc(doc_id: str, body: CourseDocIn):
    update = {**_payload(body), "updated_at": datetime.now(timezone.utc)}
    try:
        doc = _col().find_one_and_update({"_id": _oid(doc_id)}, {"$set": update}, return_document=ReturnDocument.AFTER)
    except WriteError as exc:
        raise HTTPException(status_code=422, detail=f"database validation failed: {exc.details.get('errmsg', exc)}")
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Course document {doc_id} not found")
    return _out(doc)


@router.delete("/{doc_id}", status_code=204)
def delete_doc(doc_id: str):
    result = _col().delete_one({"_id": _oid(doc_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Course document {doc_id} not found")
    return Response(status_code=204)
