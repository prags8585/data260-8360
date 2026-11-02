import subprocess
import time
import uuid

from confluent_kafka import Consumer, TopicPartition

from kafka_svc import config

KAFKA_CONTAINER = "s8360-kafka"


def probe_consumer() -> Consumer:
    return Consumer({"bootstrap.servers": config.BOOTSTRAP, "group.id": f"probe-{uuid.uuid4().hex[:8]}", "enable.auto.commit": False})


def end_offsets(topic: str) -> dict[int, int]:
    c = probe_consumer()
    meta = c.list_topics(topic, timeout=10).topics[topic]
    out = {p: c.get_watermark_offsets(TopicPartition(topic, p), timeout=10)[1] for p in meta.partitions}
    c.close()
    return out


def seed_group(group: str, topic: str) -> None:
    """Commit the group's position at the current end of the topic so a new test only sees its own messages."""
    c = Consumer({"bootstrap.servers": config.BOOTSTRAP, "group.id": group, "enable.auto.commit": False})
    c.commit(offsets=[TopicPartition(topic, p, o) for p, o in end_offsets(topic).items()], asynchronous=False)
    c.close()


def read_since(topic: str, start: dict[int, int], timeout: float = 8) -> list[dict]:
    c = probe_consumer()
    c.assign([TopicPartition(topic, p, o) for p, o in start.items()])
    wanted = sum(end_offsets(topic)[p] - o for p, o in start.items())
    found: list[dict] = []
    deadline = time.time() + timeout
    while len(found) < wanted and time.time() < deadline:
        msg = c.poll(0.5)
        if msg is not None and not msg.error():
            found.append({"partition": msg.partition(), "offset": msg.offset(), "value": (msg.value() or b"").decode("utf-8", "replace")})
    c.close()
    return found


def group_offsets(group: str, topic: str = config.TASKS_TOPIC) -> dict:
    out = subprocess.run(["docker", "exec", KAFKA_CONTAINER, "/opt/kafka/bin/kafka-consumer-groups.sh", "--bootstrap-server", "localhost:9092",
                          "--describe", "--group", group], capture_output=True, text=True)
    text = (out.stdout + out.stderr).strip()
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[1] == topic:
            rows.append({"partition": int(parts[2]), "current_offset": None if parts[3] == "-" else int(parts[3]),
                         "log_end_offset": int(parts[4]), "lag": None if parts[5] == "-" else int(parts[5])})
    return {"raw": text, "rows": rows}
