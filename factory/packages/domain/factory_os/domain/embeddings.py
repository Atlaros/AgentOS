"""Catalog vectors for pgvector.

Live: Cohere embed-v4 (search_document / search_query). Pytest and missing
key: deterministic hashed vectors of the same dimension. Structured catalog
facts still win. The LLM never sees the API key.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import Any

import httpx

from factory_os.domain.seed import tokenize

logger = logging.getLogger("factory_os.embeddings")

EMBED_DIMS = 1024
COHERE_URL = "https://api.cohere.com/v2/embed"
COHERE_BATCH = 96
_ALLOWED_DIMS = frozenset({256, 512, 1024, 1536})


def embed_dims() -> int:
    raw = (os.environ.get("COHERE_EMBED_DIMS") or "").strip()
    if not raw:
        return EMBED_DIMS
    try:
        dims = int(raw)
    except ValueError:
        return EMBED_DIMS
    if dims in _ALLOWED_DIMS:
        return dims
    return EMBED_DIMS


def embed_model() -> str:
    return (os.environ.get("COHERE_EMBED_MODEL_ID") or "embed-v4.0").strip() or "embed-v4.0"


def live_cohere_enabled() -> bool:
    if not (os.environ.get("COHERE_API_KEY") or "").strip():
        return False
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("FACTORY_OS_LIVE_EMBED") != "1":
        return False
    return True


def reindex_requested() -> bool:
    return (os.environ.get("COHERE_REINDEX") or "").strip().lower() in {"1", "true", "yes"}


def hashed_embedding(text: str, dims: int | None = None) -> list[float]:
    size = dims if dims is not None else embed_dims()
    vec = [0.0] * size
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % size
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(a * b for a, b in zip(left, right, strict=True)))


def embed_blob(record: Any) -> str:
    attrs = getattr(record, "attributes", {}) or {}
    parts = [
        getattr(record, "name", "") or "",
        getattr(record, "description", "") or "",
        getattr(record, "category", "") or "",
        str(attrs.get("codigo") or ""),
        getattr(record, "product_sku", "") or "",
        getattr(record, "variant_sku", "") or "",
    ]
    return " ".join(str(part) for part in parts if part)


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def parse_vector(raw: object) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [float(value) for value in raw]
    text = str(raw).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if not text:
        return []
    return [float(part) for part in text.split(",") if part.strip()]


def embed_query(text: str) -> list[float]:
    return embed_texts([text], input_type="search_query")[0]


def embed_document(text: str) -> list[float]:
    return embed_texts([text], input_type="search_document")[0]


def embed_documents(texts: list[str]) -> list[list[float]]:
    return embed_texts(texts, input_type="search_document")


def embed_texts(texts: list[str], *, input_type: str) -> list[list[float]]:
    if not texts:
        return []
    cleaned = [item.strip() or " " for item in texts]
    if not live_cohere_enabled():
        dims = embed_dims()
        return [hashed_embedding(item, dims) for item in cleaned]
    out: list[list[float]] = []
    for start in range(0, len(cleaned), COHERE_BATCH):
        out.extend(_cohere_embed_batch(cleaned[start : start + COHERE_BATCH], input_type=input_type))
    return out


def _cohere_embed_batch(texts: list[str], *, input_type: str) -> list[list[float]]:
    key = (os.environ.get("COHERE_API_KEY") or "").strip()
    dims = embed_dims()
    payload = {
        "model": embed_model(),
        "texts": texts,
        "input_type": input_type,
        "embedding_types": ["float"],
        "output_dimension": dims,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.post(COHERE_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise RuntimeError("cohere_embed_unavailable") from exc
    if response.status_code == 401:
        raise RuntimeError("cohere_embed_unauthorized")
    if response.status_code >= 400:
        raise RuntimeError(f"cohere_embed_http_{response.status_code}")
    vectors = _parse_cohere_embeddings(response.json())
    if len(vectors) != len(texts):
        raise RuntimeError("cohere_embed_count_mismatch")
    for vec in vectors:
        if len(vec) != dims:
            raise RuntimeError("cohere_embed_dim_mismatch")
    logger.info("cohere_embed count=%s dim=%s type=%s", len(vectors), dims, input_type)
    return vectors


def _parse_cohere_embeddings(payload: object) -> list[list[float]]:
    if not isinstance(payload, dict):
        raise RuntimeError("cohere_embed_bad_payload")
    block = payload.get("embeddings")
    rows: object = None
    if isinstance(block, dict):
        rows = block.get("float") or block.get("float_")
    elif isinstance(block, list):
        rows = block
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("cohere_embed_empty")
    return [[float(value) for value in row] for row in rows]
