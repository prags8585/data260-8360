import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, Header
from fastapi.responses import JSONResponse

from kafka_svc import config
from kafka_svc.bus import new_correlation_id, setup_logging
from kafka_svc.rpc import KafkaRpcClient

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    app.state.client = await asyncio.to_thread(lambda: KafkaRpcClient(f"{config.PREFIX}-api").start())
    log.info("FastAPI server started at http://127.0.0.1:%d (Kafka bootstrap %s)", config.PORT_BASE, config.BOOTSTRAP)
    yield
    app.state.client.close()


app = FastAPI(title="s8360 course service over Kafka", lifespan=lifespan)


def _reply(response: dict, success_status: int, correlation_id: str) -> JSONResponse:
    if response.get("success"):
        status = success_status
    elif response.get("error") == "Course not found":
        status = 404
    elif str(response.get("error", "")).startswith("No response"):
        status = 504
    else:
        status = 422
    response = {**response, "correlation_id": correlation_id}
    return JSONResponse(response, status_code=status, headers={"X-Correlation-ID": correlation_id})


@app.get("/health")
async def health():
    return {"status": "ok", "port": config.PORT_BASE, "request_topic": config.REQUEST_TOPIC, "response_topic": config.RESPONSE_TOPIC}


@app.post("/courses")
async def create_course_via_kafka(body: dict = Body(...), x_correlation_id: str | None = Header(default=None)):
    correlation_id = x_correlation_id or new_correlation_id()
    log.info("HTTP POST /courses correlation_id=%s", correlation_id)
    response = await asyncio.to_thread(app.state.client.call, "CREATE_COURSE", body, correlation_id)
    log.info("returning to caller correlation_id=%s success=%s", correlation_id, response.get("success"))
    return _reply(response, 201, correlation_id)


@app.get("/courses/{course_id}")
async def get_course_via_kafka(course_id: str, x_correlation_id: str | None = Header(default=None)):
    correlation_id = x_correlation_id or new_correlation_id()
    log.info("HTTP GET /courses/%s correlation_id=%s", course_id, correlation_id)
    response = await asyncio.to_thread(app.state.client.call, "GET_COURSE", {"course_id": course_id}, correlation_id)
    log.info("returning to caller correlation_id=%s success=%s", correlation_id, response.get("success"))
    return _reply(response, 200, correlation_id)
