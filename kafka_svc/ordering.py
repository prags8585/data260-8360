import random

from kafka_svc.brains import DEFAULT_PLAN
from kafka_svc.catalogue import COURSE_CODES

MESSAGE_COUNT = 20


def make_messages(seed: int, count: int = MESSAGE_COUNT) -> list[dict]:
    """Related messages: several updates per course, numbered per course by `seq`; work_ms is the simulated work time."""
    rng = random.Random(seed)
    next_seq: dict[str, int] = {}
    messages = []
    for i in range(count):
        entity = rng.choice(COURSE_CODES)
        next_seq[entity] = next_seq.get(entity, 0) + 1
        messages.append({
            "correlation_id": f"ord-{seed}-{i:02d}",
            "entity": entity,
            "seq": next_seq[entity],
            "question": f"Update {entity}, step {next_seq[entity]}",
            "plan": DEFAULT_PLAN,
            "work_ms": rng.randint(120, 400),
            "test": "ordering",
        })
    return messages


def analyse(trace: list[dict]) -> dict:
    """`trace` holds one record per processed message; processing order is the order of finished_at."""
    ordered = sorted(trace, key=lambda r: r["finished_at"])
    per_entity: dict[str, dict] = {}
    for position, record in enumerate(ordered, 1):
        entry = per_entity.setdefault(record["entity"], {"processed_seqs": [], "partitions": set(), "writers": set()})
        entry["processed_seqs"].append(record["seq"])
        entry["partitions"].add(record["partition"])
        entry["writers"].add(record["writer"])
        record["processing_position"] = position
    entities = {}
    for entity, entry in sorted(per_entity.items()):
        seqs = entry["processed_seqs"]
        entities[entity] = {
            "messages": len(seqs),
            "processed_seqs": seqs,
            "partitions": sorted(entry["partitions"]),
            "writers": sorted(entry["writers"]),
            "in_order": seqs == sorted(seqs),
            "inversions": sum(1 for a, b in zip(seqs, seqs[1:]) if b < a),
        }
    return {
        "messages_processed": len(ordered),
        "entities": entities,
        "entities_in_one_partition": sum(1 for e in entities.values() if len(e["partitions"]) == 1),
        "entities_in_order": sum(1 for e in entities.values() if e["in_order"]),
        "total_inversions": sum(e["inversions"] for e in entities.values()),
        "processing_order": [
            {"position": r["processing_position"], "writer": r["writer"], "partition": r["partition"], "offset": r["offset"],
             "entity": r["entity"], "seq": r["seq"], "finished_at": r["finished_at"]} for r in ordered
        ],
    }
