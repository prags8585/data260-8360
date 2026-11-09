import os

from kafka_svc import config as kafka_config

PREFIX = kafka_config.PREFIX
PORT_BASE = kafka_config.PORT_BASE
SEED = kafka_config.SEED

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6382/0")

VIEWS_SYNC_EVERY = 10

ENTRY_PREFIX = f"{PREFIX}:cache:entry:"
STATS_KEY = f"{PREFIX}:cache:stats"
INDEX_NAME = f"{PREFIX}_cache_idx"

EMBED_DIM = 384  # sentence-transformers/all-MiniLM-L6-v2 (the same model the HW6 memory service uses)
DEFAULT_THRESHOLD = 0.85
AGENT_TIMEOUT_S = 240.0


def views_key(course_id: int | str) -> str:
    return f"{PREFIX}:views:course:{course_id}"
