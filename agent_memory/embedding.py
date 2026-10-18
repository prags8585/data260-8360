import logging
from functools import lru_cache

import numpy as np

from docdb import config

log = logging.getLogger("agent_memory.embedding")


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    log.info("loading embedding model %s", config.EMBED_MODEL)
    return SentenceTransformer(config.EMBED_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    vectors = _model().encode(texts, normalize_embeddings=True)
    return [[float(x) for x in v] for v in vectors]


def cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.asarray(a), np.asarray(b)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom else 0.0
