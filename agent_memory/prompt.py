

from functools import lru_cache

import tiktoken

PRIMER = (
    "You are a friendly academic-planning assistant for a campus course catalogue. "
    "Answer in at most three short sentences. Use the memory sections when they are relevant; "
    "if you do not know something about the user, say so instead of guessing."
)


@lru_cache(maxsize=1)
def _encoder():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text)) if text else 0


def long_term_block(session_summary: str | None, lifetime_summary: str | None) -> str:
    parts = []
    if lifetime_summary:
        parts.append(f"Lifetime summary of this user:\n{lifetime_summary}")
    if session_summary:
        parts.append(f"Summary of this session so far:\n{session_summary}")
    return "\n\n".join(parts)


def episodic_block(facts: list[dict]) -> str:
    if not facts:
        return ""
    lines = "\n".join(f"- {f['fact']}" for f in facts)
    return f"[Remembered facts that may be relevant]\n{lines}"


def assemble(message: str, window: list[dict], session_summary: str | None, lifetime_summary: str | None,
             facts: list[dict]) -> tuple[list[tuple[str, str]], dict[str, int]]:
    long_term = long_term_block(session_summary, lifetime_summary)
    system = PRIMER + (f"\n\n{long_term}" if long_term else "")
    episodic = episodic_block(facts)
    final_user = message + (f"\n\n{episodic}" if episodic else "")
    messages = [("system", system)]
    messages += [(m["role"], m["content"]) for m in window]
    messages.append(("user", final_user))
    components = {
        "system_primer": count_tokens(PRIMER),
        "long_term_summary": count_tokens(long_term),
        "short_term_window": sum(count_tokens(m["content"]) for m in window),
        "current_message": count_tokens(message),
        "episodic_facts": count_tokens(episodic),
    }
    return messages, components
