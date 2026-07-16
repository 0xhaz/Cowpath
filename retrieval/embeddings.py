"""Local, on-device embeddings via sentence-transformers.

Same model is used at index time (indexer) and query time (retrieval) so the
vectors live in one space. Small + CPU-fine; swap up only if retrieval quality
is visibly weak (techstacks §2).
"""

from __future__ import annotations

import os
from functools import lru_cache

from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def _model(name: str) -> SentenceTransformer:
    return SentenceTransformer(name)


def embed(texts: list[str], model: str = DEFAULT_MODEL) -> list[list[float]]:
    """Embed a batch of texts into unit-normalized vectors."""
    vecs = _model(model).encode(
        texts, normalize_embeddings=True, convert_to_numpy=True
    )
    return vecs.tolist()


def embed_one(text: str, model: str = DEFAULT_MODEL) -> list[float]:
    return embed([text], model)[0]


def dim(model: str = DEFAULT_MODEL) -> int:
    m = _model(model)
    getter = getattr(m, "get_embedding_dimension", None) or \
        m.get_sentence_embedding_dimension
    return getter()
