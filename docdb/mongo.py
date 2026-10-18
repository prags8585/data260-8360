import logging
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import CollectionInvalid

from docdb import config

log = logging.getLogger("docdb.mongo")

STATUSES = ["open", "waitlist", "closed"]
CATEGORIES = ["Computer Science", "Data Science", "Business", "Engineering"]

COURSE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["title", "status", "category", "start_date", "created_at", "updated_at"],
        "additionalProperties": False,
        "properties": {
            "_id": {"bsonType": "objectId"},
            "title": {"bsonType": "string", "minLength": 1, "maxLength": 100},
            "description": {"bsonType": ["string", "null"], "maxLength": 1000},
            "status": {"enum": STATUSES},
            "category": {"enum": CATEGORIES},
            "start_date": {"bsonType": "date"},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
        },
    }
}

MESSAGE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "session_id", "role", "content", "created_at"],
        "properties": {
            "user_id": {"bsonType": "string"},
            "session_id": {"bsonType": "string"},
            "role": {"enum": ["user", "assistant"]},
            "content": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    }
}

SUMMARY_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "scope", "text", "created_at"],
        "properties": {
            "user_id": {"bsonType": "string"},
            "session_id": {"bsonType": ["string", "null"]},
            "scope": {"enum": ["session", "user"]},
            "text": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    }
}

EPISODE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["user_id", "session_id", "fact", "importance", "embedding", "created_at"],
        "properties": {
            "user_id": {"bsonType": "string"},
            "session_id": {"bsonType": "string"},
            "fact": {"bsonType": "string", "maxLength": 300},
            "importance": {"bsonType": ["double", "int"], "minimum": 0, "maximum": 1},
            "embedding": {"bsonType": "array", "items": {"bsonType": ["double", "int"]}},
            "created_at": {"bsonType": "date"},
        },
    }
}

COLLECTIONS = {
    config.COURSE_COLLECTION: COURSE_VALIDATOR,
    "messages": MESSAGE_VALIDATOR,
    "summaries": SUMMARY_VALIDATOR,
    "episodes": EPISODE_VALIDATOR,
}


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=3000, tz_aware=True)


def get_db() -> Database:
    return get_client()[config.DB_NAME]


def ensure_collections(db: Database | None = None) -> list[str]:
    """Creates each collection with its validator (or updates the validator
    if it already exists) and adds the indexes. Idempotent."""
    db = db if db is not None else get_db()
    for name, validator in COLLECTIONS.items():
        try:
            db.create_collection(name, validator=validator, validationLevel="strict", validationAction="error")
        except CollectionInvalid:
            db.command("collMod", name, validator=validator, validationLevel="strict", validationAction="error")
    db[config.COURSE_COLLECTION].create_index([("category", ASCENDING), ("status", ASCENDING)])
    db["messages"].create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", DESCENDING)])
    db["summaries"].create_index([("user_id", ASCENDING), ("scope", ASCENDING), ("created_at", DESCENDING)])
    db["episodes"].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    return sorted(COLLECTIONS)
