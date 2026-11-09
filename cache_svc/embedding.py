import os
from functools import lru_cache

import numpy as np

from docdb import config as docdb_config


@lru_cache(maxsize=1)
def _model():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # the model is already cached locally; no network check on every start
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(docdb_config.EMBED_MODEL, device="cpu")  # CPU only: stable timings next to the Ollama model on the GPU


def embed(texts: list[str]) -> list[np.ndarray]:
    """Unit-length vectors, so cosine similarity is a dot product."""
    return list(_model().encode(texts, normalize_embeddings=True, show_progress_bar=False))
