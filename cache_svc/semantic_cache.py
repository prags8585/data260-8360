import logging
import time
import uuid

import numpy as np
import redis
from redis.commands.search.field import NumericField, TagField, TextField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query

from cache_svc import config

log = logging.getLogger("semantic_cache")


def to_bytes(vector) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


class SemanticCache:
    """Query -> answer cache in Redis. Every entry is a hash with the query, its embedding, the final answer and a
    data-version marker; a vector index (cosine) finds the nearest cached query for a new one."""

    def __init__(self, client: redis.Redis | None = None):
        self.client = client or redis.Redis.from_url(config.REDIS_URL)  # bytes in, bytes out: the vectors are binary
        self.search = self.client.ft(config.INDEX_NAME)

    def ensure_index(self) -> None:
        try:
            self.search.info()
            return
        except redis.ResponseError:
            pass
        schema = (
            TextField("query"),
            TextField("answer"),
            TagField("data_version"),
            TextField("deps"),
            NumericField("created_at"),
            VectorField("embedding", "FLAT", {"TYPE": "FLOAT32", "DIM": config.EMBED_DIM, "DISTANCE_METRIC": "COSINE"}),
        )
        self.search.create_index(schema, definition=IndexDefinition(prefix=[config.ENTRY_PREFIX], index_type=IndexType.HASH))
        log.info("created vector index %s on %s* (dim %d, cosine)", config.INDEX_NAME, config.ENTRY_PREFIX, config.EMBED_DIM)

    def lookup(self, vector) -> dict | None:
        """Nearest cached query: {key, query, answer, data_version, deps, similarity}, or None when the cache is empty."""
        query = (Query("*=>[KNN 1 @embedding $vec AS dist]").return_fields("query", "answer", "data_version", "deps", "dist")
                 .sort_by("dist").dialect(2))
        found = self.search.search(query, query_params={"vec": to_bytes(vector)})
        if not found.docs:
            return None
        doc = found.docs[0]
        return {"key": doc.id, "query": _text(doc.query), "answer": _text(doc.answer), "data_version": _text(doc.data_version),
                "deps": _text(doc.deps), "similarity": round(1.0 - float(doc.dist), 4)}

    def store(self, question: str, vector, answer: str, data_version: str, deps: str) -> str:
        key = f"{config.ENTRY_PREFIX}{uuid.uuid4().hex[:12]}"
        self.client.hset(key, mapping={"query": question, "answer": answer, "data_version": data_version, "deps": deps,
                                       "created_at": time.time(), "embedding": to_bytes(vector)})
        return key

    def delete(self, key: str) -> None:
        self.client.delete(key)

    def flush(self) -> int:
        keys = list(self.client.scan_iter(match=f"{config.ENTRY_PREFIX}*"))
        if keys:
            self.client.delete(*keys)
        return len(keys)

    def size(self) -> int:
        return sum(1 for _ in self.client.scan_iter(match=f"{config.ENTRY_PREFIX}*"))

    # ---- counters (hit rate and average latency across requests) ------------------------------------------------
    def record(self, outcome: str, latency_ms: float) -> None:
        self.client.hincrby(config.STATS_KEY, outcome, 1)
        self.client.hincrbyfloat(config.STATS_KEY, f"{outcome}_latency_ms", latency_ms)

    def reset_stats(self) -> None:
        self.client.delete(config.STATS_KEY)

    def stats(self) -> dict:
        raw = {k.decode(): float(v) for k, v in self.client.hgetall(config.STATS_KEY).items()}
        hits, misses = int(raw.get("hit", 0)), int(raw.get("miss", 0))
        total = hits + misses
        return {"queries": total, "hits": hits, "misses": misses, "stale_invalidated": int(raw.get("stale", 0)),
                "hit_rate": round(hits / total, 4) if total else 0.0,
                "avg_latency_ms_hit": round(raw.get("hit_latency_ms", 0.0) / hits, 2) if hits else None,
                "avg_latency_ms_miss": round(raw.get("miss_latency_ms", 0.0) / misses, 2) if misses else None}


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
