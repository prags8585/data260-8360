import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from docdb import config
from docdb.mongo import ensure_collections

log = logging.getLogger("docdb.server")
ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8260"]


def register(app: FastAPI) -> None:
    from agent_memory.routes import router as memory_router
    from docdb.routes import router as course_router

    if not any(m.cls is CORSMiddleware for m in app.user_middleware):
        app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True,
                           allow_methods=["*"], allow_headers=["*"])
    app.include_router(course_router)
    app.include_router(memory_router)

    @app.exception_handler(ServerSelectionTimeoutError)
    async def mongo_down(request: Request, exc: ServerSelectionTimeoutError):
        log.error("MongoDB unreachable at %s", config.MONGO_URI)
        return JSONResponse(status_code=503, content={"detail": "MongoDB is unavailable"})

    @app.exception_handler(PyMongoError)
    async def mongo_error(request: Request, exc: PyMongoError):
        log.exception("unexpected MongoDB error")
        return JSONResponse(status_code=500, content={"detail": f"database error: {type(exc).__name__}"})

    try:
        ensure_collections()
    except PyMongoError as exc:  # server still starts; routes answer 503 until Mongo is up
        log.warning("could not initialise MongoDB collections: %s", exc)
