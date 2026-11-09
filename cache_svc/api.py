import logging
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from cache_svc import config
from cache_svc.agent_client import AgentClient
from cache_svc.course_db import CourseDB
from cache_svc.embedding import embed
from cache_svc.ingress import QAIngress
from cache_svc.semantic_cache import SemanticCache
from kafka_svc.bus import setup_logging

log = logging.getLogger("cache_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    db = CourseDB()
    cache = SemanticCache()
    cache.ensure_index()
    for _ in range(3):  # load the embedding model and warm it up so the first request is not slower than the rest
        embed(["warm-up", "How many seats are available in DATA-260?", "Which department has the most seats?"])
    agent = AgentClient()
    app.state.db, app.state.cache, app.state.ingress = db, cache, QAIngress(cache, db, agent.ask)
    log.info("FastAPI server started at http://127.0.0.1:%d (Redis %s, index %s, threshold %.2f)", config.PORT_BASE, config.REDIS_URL,
             config.INDEX_NAME, config.DEFAULT_THRESHOLD)
    yield
    agent.close()


app = FastAPI(title="s8360 semantic response cache", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "port": config.PORT_BASE, "cached_entries": app.state.cache.size()}


@app.post("/ask")
def ask(body: dict = Body(...)):
    question = body.get("question")
    if not isinstance(question, str) or not question.strip():
        raise HTTPException(422, "question must be a non-empty string")
    return app.state.ingress.ask(question.strip(), threshold=body.get("threshold"), validate_version=body.get("validate_version"))


@app.get("/courses/{course_id}")
def get_course(course_id: int):
    course = app.state.db.get_course(course_id)
    if course is None:
        raise HTTPException(404, "Course not found")
    course["views"] = app.state.db.increment_course_views(course_id)
    return JSONResponse(course)


@app.get("/cache/stats")
def cache_stats():
    return {**app.state.cache.stats(), "cached_entries": app.state.cache.size()}


@app.delete("/cache")
def flush_cache():
    app.state.cache.reset_stats()
    return {"deleted_entries": app.state.cache.flush()}
