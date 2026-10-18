import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SID4 = 8360
PREFIX = f"s{SID4}"

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB", f"{PREFIX}_doc")
COURSE_COLLECTION = "course_documents"

# --- Part 2 / Part 3 memory settings (all overridable by environment) ---
SHORT_TERM_N = int(os.environ.get("SHORT_TERM_N", "12"))
SUMMARIZE_EVERY_USER_MSGS = int(os.environ.get("SUMMARIZE_EVERY_USER_MSGS", "5"))
LIFETIME_EVERY_N_SUMMARIES = int(os.environ.get("LIFETIME_EVERY_N_SUMMARIES", "3"))
EPISODE_TOP_K = int(os.environ.get("EPISODE_TOP_K", "3"))
MAX_FACTS_PER_MESSAGE = 3

LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3:8b")
REPLY_MAX_TOKENS = int(os.environ.get("REPLY_MAX_TOKENS", "160"))
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

USAGE_LOG_PATH = Path(os.environ.get("USAGE_LOG_PATH", ROOT / "reports/hw06/raw/chat_usage_log.csv"))
