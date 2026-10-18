
from datetime import datetime, timezone
from typing import Any

from docdb.mongo import get_db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def save_message(user_id: str, session_id: str, role: str, content: str) -> dict[str, Any]:
    doc = {"user_id": user_id, "session_id": session_id, "role": role, "content": content, "created_at": _now()}
    doc["_id"] = get_db()["messages"].insert_one(doc).inserted_id
    return doc


def recent_messages(user_id: str, session_id: str, limit: int, before_id=None) -> list[dict]:
    query: dict[str, Any] = {"user_id": user_id, "session_id": session_id}
    if before_id is not None:
        query["_id"] = {"$lt": before_id}
    rows = list(get_db()["messages"].find(query).sort("_id", -1).limit(limit))
    return list(reversed(rows))


def count_user_messages(user_id: str, session_id: str) -> int:
    return get_db()["messages"].count_documents({"user_id": user_id, "session_id": session_id, "role": "user"})


def latest_summary(user_id: str, scope: str, session_id: str | None = None) -> dict | None:
    query: dict[str, Any] = {"user_id": user_id, "scope": scope}
    if scope == "session":
        query["session_id"] = session_id
    return get_db()["summaries"].find_one(query, sort=[("_id", -1)])


def save_summary(user_id: str, session_id: str | None, scope: str, text: str) -> dict:
    doc = {"user_id": user_id, "session_id": session_id, "scope": scope, "text": text, "created_at": _now()}
    doc["_id"] = get_db()["summaries"].insert_one(doc).inserted_id
    return doc


def session_summaries(user_id: str, limit: int) -> list[dict]:
    rows = get_db()["summaries"].find({"user_id": user_id, "scope": "session"}).sort("_id", -1).limit(limit)
    return list(reversed(list(rows)))


def count_session_summaries(user_id: str) -> int:
    return get_db()["summaries"].count_documents({"user_id": user_id, "scope": "session"})


def save_episode(user_id: str, session_id: str, fact: str, importance: float, embedding: list[float]) -> dict:
    doc = {"user_id": user_id, "session_id": session_id, "fact": fact, "importance": float(importance),
           "embedding": embedding, "created_at": _now()}
    doc["_id"] = get_db()["episodes"].insert_one(doc).inserted_id
    return doc


def user_episodes(user_id: str, limit: int | None = None) -> list[dict]:
    cursor = get_db()["episodes"].find({"user_id": user_id}).sort("_id", -1)
    return list(cursor.limit(limit)) if limit else list(cursor)
