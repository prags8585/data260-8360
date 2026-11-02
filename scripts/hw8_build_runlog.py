#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CON = ROOT / "reports/hw08/raw/console"
PARTS = [
    ("01_stack_up.txt", "docker compose -f docker-compose.kafka.yml up -d --build", "Part 1 - Kafka, worker and FastAPI containers started from scratch; topics created"),
    ("02_demo_kafka.txt", "PYTHONPATH=. python homework_demo.py", "Part 1 - CREATE_COURSE -> GET_COURSE through the Kafka client (10-step demonstration)"),
    ("03_demo_api.txt", "PYTHONPATH=. python homework_demo.py --via api", "Part 1 - the same flow through the FastAPI wrapper"),
    ("05_api_curl.txt", "curl against http://127.0.0.1:8260", "Part 1 - FastAPI wrapper with curl (X-Correlation-ID)"),
    ("04_part1_errors.txt", "PYTHONPATH=. python scripts/hw8_part1_errors.py", "Part 1 - unknown id, unknown operation, invalid fields"),
    ("06_part2_pipeline.txt", "python planner.py / writer.py / reviewer.py / send_question.py", "Part 2 - three agents in separate processes, two questions"),
    ("07_failure_tests.txt", "PYTHONPATH=. python scripts/hw8_failure_tests.py all", "Part 3 - duplicate delivery, consumer death, poison message, ordering"),
    ("08_dead_letter_topic.txt", "kafka-console-consumer.sh --topic s8360_dead_letter", "Part 3 - the dead-letter topic"),
    ("09_tests_and_verify.txt", "python tests_hw8.py && PYTHONPATH=. python verify_hw08.py", "Offline tests and the smoke test (writes reports/hw08/verification.json)"),
]


def main() -> None:
    out = ["# RUN_LOG.txt - DATA-260 Homework 8 (Karthik Pragada, SID4 8360, PORT_BASE 8260)",
           "# Real console output captured on a MacBook Air (Apple M4, 16 GB): Kafka 3.8.0 (KRaft), worker and FastAPI in Docker, Ollama qwen3:8b for the Part 2 agents.",
           "# Container log lines are in UTC (the trailing Z); the '=== date ===' headers are local time (PST). Each block was produced by the command shown above it.", ""]
    for name, cmd, title in PARTS:
        f = CON / name
        if f.exists():
            out += ["=" * 100, f"## {title}", f"$ {cmd}", "=" * 100, f.read_text().rstrip("\n"), ""]
    (ROOT / "reports/hw08/RUN_LOG.txt").write_text("\n".join(out))
    print("RUN_LOG lines:", len(out))


if __name__ == "__main__":
    main()
