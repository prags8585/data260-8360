import logging
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from agent_memory import service

log = logging.getLogger("agent_memory.routes")
router = APIRouter(prefix="/api", tags=["memory"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    user_id: str = Field(min_length=1, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=2000)
    # experiment overrides (default: values from docdb/config.py)
    short_term_n: int | None = Field(default=None, ge=1, le=200)
    policy: Literal["none", "compress"] | None = None


@router.post("/chat")
def chat(body: ChatRequest):
    return service.chat_turn(body.user_id, body.session_id, body.message, body.short_term_n, body.policy)


@router.get("/memory/{user_id}")
def get_memory(user_id: str):
    return service.memory_view(user_id)


@router.get("/aggregate/{user_id}")
def get_aggregate(user_id: str):
    return service.aggregate_view(user_id)
