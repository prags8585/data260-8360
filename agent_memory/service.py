import logging
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from agent_memory import episodes, prompt, store, summaries, usage_log
from agent_memory.policies import apply_policy
from docdb import config
from docdb.mongo import get_db
from src.model_client import ModelClient

log = logging.getLogger("agent_memory.service")


@lru_cache(maxsize=1)
def _models() -> dict[str, ModelClient]:
    return {
        "chat": ModelClient(config.LLM_MODEL, 0.0, num_predict=config.REPLY_MAX_TOKENS),
        "extract": ModelClient(config.LLM_MODEL, 0.0, num_predict=140, json_mode=True),
        "summary": ModelClient(config.LLM_MODEL, 0.0, num_predict=220),
    }


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def chat_turn(user_id: str, session_id: str | None, message: str, short_term_n: int | None = None,
              policy: str | None = None, usage_path=None) -> dict:
    t0 = time.perf_counter()
    models = _models()
    session_id = session_id or f"s-{uuid.uuid4().hex[:8]}"
    n = short_term_n or config.SHORT_TERM_N
    policy = policy or "none"

    saved = store.save_message(user_id, session_id, "user", message)              # 1. save user message
    window_rows = store.recent_messages(user_id, session_id, n, before_id=saved["_id"])   # 2. short-term window
    window = apply_policy(window_rows, policy)
    session_sum = store.latest_summary(user_id, "session", session_id)           # 3. long-term summaries
    lifetime_sum = store.latest_summary(user_id, "user")
    facts = episodes.retrieve_top_k(user_id, message)                             # 4. episodic retrieval

    messages, components = prompt.assemble(                                       # 5. compose prompt
        message, window, session_sum["text"] if session_sum else None,
        lifetime_sum["text"] if lifetime_sum else None, facts)

    t_model = time.perf_counter()
    result = models["chat"].complete(messages)                                    # 6. call local model
    model_ms = _ms(t_model)
    reply = result.content.strip()
    store.save_message(user_id, session_id, "assistant", reply)                   # 7. save reply

    new_facts, ep_p, ep_c = episodes.extract_facts(models["extract"], message)    # 8. memory maintenance
    episodes.store_facts(user_id, session_id, new_facts)
    user_count = store.count_user_messages(user_id, session_id)
    sums = summaries.update_summaries(models["summary"], user_id, session_id, user_count)

    latency = _ms(t0)
    usage = {
        "prompt_tokens": result.input_tokens, "completion_tokens": result.output_tokens,
        "components": components, "latency_ms": latency, "model_latency_ms": model_ms,
        "overhead_prompt_tokens": ep_p + sums["prompt_tokens"],
        "overhead_completion_tokens": ep_c + sums["completion_tokens"],
    }
    usage_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "user_id": user_id,
        "session_id": session_id, "turn": user_count, "short_term_n": n, "policy": policy,
        "prompt_tokens": result.input_tokens, "completion_tokens": result.output_tokens,
        "total_tokens": result.input_tokens + result.output_tokens,
        "primer_tokens": components["system_primer"], "long_term_tokens": components["long_term_summary"],
        "window_tokens": components["short_term_window"], "episodic_tokens": components["episodic_facts"],
        "current_tokens": components["current_message"],
        "overhead_prompt_tokens": usage["overhead_prompt_tokens"],
        "overhead_completion_tokens": usage["overhead_completion_tokens"],
        "latency_ms": latency, "model_latency_ms": model_ms, "window_messages": len(window),
        "episodes_retrieved": len(facts), "summarized": int(sums["session_summary"]),
    }, usage_path)
    return {
        "reply": reply, "session_id": session_id, "user_id": user_id,
        "used": {
            "short_term_count": len(window),
            "short_term_messages": [{"role": m["role"], "content": m["content"]} for m in window],
            "session_summary": session_sum["text"] if session_sum else None,
            "long_term_summary": lifetime_sum["text"] if lifetime_sum else None,
            "episodic_facts": facts,
        },
        "memory_updates": {"facts_extracted": new_facts, "session_summary_written": sums["session_summary"],
                           "lifetime_summary_written": sums["lifetime_summary"]},
        "usage": usage,
        "settings": {"short_term_n": n, "policy": policy},
    }


def memory_view(user_id: str) -> dict:
    """Data for GET /api/memory/{user_id}."""
    msgs = get_db()["messages"].find({"user_id": user_id}).sort("_id", -1).limit(16)
    eps = store.user_episodes(user_id, 20)

    def clean(doc: dict) -> dict:
        return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in doc.items() if k not in ("_id", "embedding")}

    session_sum = get_db()["summaries"].find_one({"user_id": user_id, "scope": "session"}, sort=[("_id", -1)])
    lifetime_sum = store.latest_summary(user_id, "user")
    return {
        "user_id": user_id,
        "last_messages": [clean(m) for m in reversed(list(msgs))],
        "latest_session_summary": clean(session_sum) if session_sum else None,
        "latest_lifetime_summary": clean(lifetime_sum) if lifetime_sum else None,
        "episodic_facts": [{**clean(e), "embedding_dim": len(e["embedding"])} for e in eps],
    }


def aggregate_view(user_id: str) -> dict:
    """Data for GET /api/aggregate/{user_id}."""
    db = get_db()
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                    "messages": {"$sum": 1},
                    "user_messages": {"$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}},
                    "assistant_messages": {"$sum": {"$cond": [{"$eq": ["$role", "assistant"]}, 1, 0]}}}},
        {"$sort": {"_id": 1}},
    ]
    daily = [{"date": d["_id"], "messages": d["messages"], "user_messages": d["user_messages"],
              "assistant_messages": d["assistant_messages"]} for d in db["messages"].aggregate(pipeline)]
    recent = db["summaries"].find({"user_id": user_id}).sort("_id", -1).limit(5)
    return {
        "user_id": user_id,
        "daily_message_counts": daily,
        "total_messages": sum(d["messages"] for d in daily),
        "recent_summaries": [{"scope": s["scope"], "session_id": s.get("session_id"), "text": s["text"],
                              "created_at": s["created_at"].isoformat()} for s in recent],
    }
