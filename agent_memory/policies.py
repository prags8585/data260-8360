import re

KEEP_VERBATIM = 4
MAX_WORDS = 20


def first_sentence(text: str, max_words: int = MAX_WORDS) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    words = sentence.split()
    return " ".join(words[:max_words]) + (" ..." if len(words) > max_words else "")


def compress_window(window: list[dict]) -> list[dict]:
    cutoff = max(0, len(window) - KEEP_VERBATIM)
    out = []
    for i, msg in enumerate(window):
        if i < cutoff and msg["role"] == "assistant":
            out.append({**msg, "content": first_sentence(msg["content"])})
        else:
            out.append(msg)
    return out


def apply_policy(window: list[dict], policy: str) -> list[dict]:
    return compress_window(window) if policy == "compress" else window
