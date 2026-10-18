import csv
import threading
from pathlib import Path

from docdb import config

FIELDS = [
    "timestamp", "user_id", "session_id", "turn", "short_term_n", "policy",
    "prompt_tokens", "completion_tokens", "total_tokens",
    "primer_tokens", "long_term_tokens", "window_tokens", "episodic_tokens", "current_tokens",
    "overhead_prompt_tokens", "overhead_completion_tokens",
    "latency_ms", "model_latency_ms", "window_messages", "episodes_retrieved", "summarized",
]
_lock = threading.Lock()


def append(row: dict, path: Path | None = None) -> None:
    target = Path(path or config.USAGE_LOG_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        is_new = not target.exists()
        with open(target, "a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
            if is_new:
                writer.writeheader()
            writer.writerow(row)
