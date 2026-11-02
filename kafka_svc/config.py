import os

SID4 = "8360"
PREFIX = f"s{SID4}"
PORT_BASE = 8000 + int(SID4) % 900
SEED = int(SID4)
VERIFY_SEED = 260000 + int(SID4)

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")

REQUEST_TOPIC = f"{PREFIX}_entity_requests"
RESPONSE_TOPIC = f"{PREFIX}_entity_responses"
INBOX_TOPIC = f"{PREFIX}_inbox"
TASKS_TOPIC = f"{PREFIX}_tasks"
DRAFTS_TOPIC = f"{PREFIX}_drafts"
FINAL_TOPIC = f"{PREFIX}_final"
DEAD_LETTER_TOPIC = f"{PREFIX}_dead_letter"

TOPIC_PARTITIONS = {
    REQUEST_TOPIC: 1,
    RESPONSE_TOPIC: 1,
    INBOX_TOPIC: 1,
    TASKS_TOPIC: 2,
    DRAFTS_TOPIC: 1,
    FINAL_TOPIC: 1,
    DEAD_LETTER_TOPIC: 1,
}

WORKER_GROUP = f"{PREFIX}_entity_worker"
PLANNER_GROUP = f"{PREFIX}_planner"
WRITER_GROUP = f"{PREFIX}_writers"
REVIEWER_GROUP = f"{PREFIX}_reviewer"

MODEL = "qwen3:8b"
