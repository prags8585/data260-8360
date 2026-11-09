import logging
import re
import time
from typing import Callable

from cache_svc import config
from cache_svc.course_db import CourseDB
from cache_svc.embedding import embed
from cache_svc.semantic_cache import SemanticCache

log = logging.getLogger("ingress")
COURSE_CODE = re.compile(r"\b[A-Z]{2,5}-\d{2,3}[A-Z]?\b")


def deps_of(question: str) -> list[str]:
    """Course codes the answer depends on (all courses when the question names none)."""
    return sorted(set(COURSE_CODE.findall(question)))


class QAIngress:
    """The semantic cache in front of the HW8 agent pipeline.

    hit  : the nearest cached query is at least `threshold` similar (and, when validate_version is on, the
           course rows its answer came from have not changed) -> return the stored final answer, no agent run
    miss : run the pipeline (agent(question) -> final message), store query + embedding + answer + data version
    """

    def __init__(self, cache: SemanticCache, db: CourseDB, agent: Callable[[str], dict],
                 threshold: float = config.DEFAULT_THRESHOLD, validate_version: bool = True):
        self.cache, self.db, self.agent = cache, db, agent
        self.threshold, self.validate_version = threshold, validate_version

    def ask(self, question: str, *, threshold: float | None = None, validate_version: bool | None = None,
            store: bool = True, track: bool = True) -> dict:
        threshold = self.threshold if threshold is None else threshold
        validate_version = self.validate_version if validate_version is None else validate_version
        t0 = time.perf_counter()
        log.info("ask start question=%r threshold=%.2f", question, threshold)

        t = time.perf_counter()
        vector = embed([question])[0]
        embed_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        nearest = self.cache.lookup(vector)
        search_ms = (time.perf_counter() - t) * 1000
        similarity = nearest["similarity"] if nearest else None
        log.info("embedding %.1f ms, vector search %.1f ms, nearest similarity=%s", embed_ms, search_ms, similarity)

        stale, check_ms = False, None
        if nearest and nearest["similarity"] >= threshold:
            if validate_version:
                t = time.perf_counter()
                deps = [c for c in nearest["deps"].split(",") if c and c != "*"]
                current = self.db.data_version(deps or None)
                check_ms = (time.perf_counter() - t) * 1000
                stale = current != nearest["data_version"]
                log.info("data-version check %.1f ms: stored=%s current=%s -> %s", check_ms, nearest["data_version"], current,
                         "STALE" if stale else "fresh")
            if not stale:
                latency_ms = (time.perf_counter() - t0) * 1000
                log.info("cache HIT similarity=%.4f threshold=%.2f matched_query=%r latency_ms=%.1f", similarity, threshold, nearest["query"], latency_ms)
                if track:
                    self.cache.record("hit", latency_ms)
                return {"question": question, "answer": nearest["answer"], "status": "approved", "is_cached": True, "similarity": similarity,
                        "latency_ms": round(latency_ms, 1), "cached_query": nearest["query"], "cache_key": nearest["key"],
                        "stale_invalidated": False, "threshold": threshold, "data_version": nearest["data_version"],
                        "version_check_ms": None if check_ms is None else round(check_ms, 1)}
            self.cache.delete(nearest["key"])
            if track:
                self.cache.client.hincrby(config.STATS_KEY, "stale", 1)

        log.info("cache MISS best_similarity=%s threshold=%.2f -> running the agent pipeline", similarity, threshold)
        t = time.perf_counter()
        final = self.agent(question)
        agent_ms = (time.perf_counter() - t) * 1000
        answer = final.get("answer")
        log.info("agent pipeline finished status=%s in %.0f ms", final.get("status"), agent_ms)

        key, version = None, None
        if store and final.get("status") == "approved" and answer:
            codes = deps_of(question)
            version = self.db.data_version(codes or None)
            key = self.cache.store(question, vector, answer, version, ",".join(codes) or "*")
            log.info("cache STORE key=%s data_version=%s deps=%s", key, version, ",".join(codes) or "*")
        latency_ms = (time.perf_counter() - t0) * 1000
        if track:
            self.cache.record("miss", latency_ms)
        return {"question": question, "answer": answer, "status": final.get("status"), "is_cached": False, "similarity": similarity,
                "latency_ms": round(latency_ms, 1), "cached_query": nearest["query"] if nearest else None, "cache_key": key,
                "stale_invalidated": stale, "threshold": threshold, "correlation_id": final.get("correlation_id"),
                "data_version": version, "version_check_ms": None if check_ms is None else round(check_ms, 1)}
