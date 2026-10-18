import logging

from agent_memory import store
from docdb import config

log = logging.getLogger("agent_memory.summaries")

SESSION_SYSTEM = (
    "Summarise the conversation into at most 5 concise bullet points that capture durable facts about the user "
    "and their plans. Keep names, dates and preferences exactly. Start each bullet with '- '."
)
LIFETIME_SYSTEM = (
    "Condense these session summaries into at most 6 concise bullet points of lifetime facts about the user. "
    "Merge duplicates; if two facts conflict keep the most recent one. Start each bullet with '- '."
)


def should_summarize(user_message_count: int) -> bool:
    return user_message_count > 0 and user_message_count % config.SUMMARIZE_EVERY_USER_MSGS == 0


def summarize_session(llm, previous: str | None, recent: list[dict]) -> tuple[str, int, int]:
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
    prior = f"Previous summary:\n{previous}\n\n" if previous else ""
    result = llm.complete([("system", SESSION_SYSTEM), ("user", f"{prior}Recent messages:\n{transcript}")])
    return result.content.strip(), result.input_tokens, result.output_tokens


def condense_lifetime(llm, previous: str | None, session_texts: list[str]) -> tuple[str, int, int]:
    body = "\n\n".join(f"Session summary {i + 1}:\n{t}" for i, t in enumerate(session_texts))
    prior = f"Existing lifetime summary:\n{previous}\n\n" if previous else ""
    result = llm.complete([("system", LIFETIME_SYSTEM), ("user", f"{prior}{body}")])
    return result.content.strip(), result.input_tokens, result.output_tokens


def update_summaries(llm, user_id: str, session_id: str, user_msg_count: int) -> dict:
    """Runs the summarisation trigger. Returns what happened and the tokens spent."""
    info = {"session_summary": False, "lifetime_summary": False, "prompt_tokens": 0, "completion_tokens": 0}
    if not should_summarize(user_msg_count):
        return info
    previous = store.latest_summary(user_id, "session", session_id)
    recent = store.recent_messages(user_id, session_id, config.SUMMARIZE_EVERY_USER_MSGS * 2)
    text, p, c = summarize_session(llm, previous["text"] if previous else None, recent)
    store.save_summary(user_id, session_id, "session", text)
    info.update(session_summary=True, prompt_tokens=p, completion_tokens=c)

    if store.count_session_summaries(user_id) % config.LIFETIME_EVERY_N_SUMMARIES == 0:
        sessions = [s["text"] for s in store.session_summaries(user_id, 5)]
        prior = store.latest_summary(user_id, "user")
        life, p2, c2 = condense_lifetime(llm, prior["text"] if prior else None, sessions)
        store.save_summary(user_id, None, "user", life)
        info["lifetime_summary"] = True
        info["prompt_tokens"] += p2
        info["completion_tokens"] += c2
    return info
