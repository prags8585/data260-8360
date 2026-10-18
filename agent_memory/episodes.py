import json
import logging

from agent_memory import store
from agent_memory.embedding import cosine, embed
from docdb import config

log = logging.getLogger("agent_memory.episodes")

EXTRACT_SYSTEM = (
    "You extract durable facts about the USER from one chat message. "
    f"Return JSON only: {{\"facts\": [{{\"fact\": \"<max 15 words>\", \"importance\": <0.0-1.0>}}]}} with at most "
    f"{config.MAX_FACTS_PER_MESSAGE} facts. Facts are things worth remembering later: names, preferences, plans, "
    "constraints, people, schedules. Importance is higher for facts that would be costly to forget. "
    "If the message contains no durable fact about the user, return {\"facts\": []}."
)


def parse_facts(raw: str) -> list[dict]:
    """Tolerant parser: returns at most MAX_FACTS_PER_MESSAGE cleaned facts."""
    try:
        data = json.loads(raw)
        items = data.get("facts", []) if isinstance(data, dict) else []
    except ValueError:
        return []
    facts = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("fact"), str):
            continue
        text = item["fact"].strip()[:300]
        try:
            importance = min(1.0, max(0.0, float(item.get("importance", 0.5))))
        except (TypeError, ValueError):
            importance = 0.5
        if text:
            facts.append({"fact": text, "importance": round(importance, 2)})
    return facts[: config.MAX_FACTS_PER_MESSAGE]


def extract_facts(llm, message: str) -> tuple[list[dict], int, int]:
    """Returns (facts, prompt_tokens, completion_tokens) for the extraction call."""
    result = llm.complete([("system", EXTRACT_SYSTEM), ("user", message)])
    return parse_facts(result.content), result.input_tokens, result.output_tokens


def store_facts(user_id: str, session_id: str, facts: list[dict]) -> list[dict]:
    if not facts:
        return []
    known = {e["fact"].lower() for e in store.user_episodes(user_id)}
    fresh = [f for f in facts if f["fact"].lower() not in known]
    if not fresh:
        return []
    vectors = embed([f["fact"] for f in fresh])
    return [store.save_episode(user_id, session_id, f["fact"], f["importance"], v) for f, v in zip(fresh, vectors)]


def retrieve_top_k(user_id: str, query: str, k: int = config.EPISODE_TOP_K) -> list[dict]:
    """Top-k episodes by cosine similarity to the current message embedding."""
    episodes = store.user_episodes(user_id)
    if not episodes:
        return []
    query_vec = embed([query])[0]
    scored = [(cosine(query_vec, e["embedding"]), e) for e in episodes]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [{"fact": e["fact"], "importance": e["importance"], "score": round(s, 4)} for s, e in scored[:k]]
