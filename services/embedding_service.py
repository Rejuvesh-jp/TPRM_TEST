"""
Embedding Service
=================
Provides text embedding via OpenAI API or deterministic mock.
Mock embeddings use SHA-256 seeded PRNG for reproducible 1536-dim vectors.
Includes an embedding cache to guarantee identical embeddings for identical text.
"""

import hashlib
import json as _json
import logging
import random

import numpy as np

logger = logging.getLogger("tprm.embedding_service")

EMBEDDING_DIM = 1536

# ── Embedding cache ─────────────────────────────────────
# Guarantees the same text always produces the exact same embedding vector.
# Without this, the OpenAI Embeddings API can return slightly different vectors
# for the same text across calls, causing downstream prompt differences.
_embedding_cache: dict[str, list[float]] = {}


def _emb_cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _get_cached_embedding(text: str) -> list[float] | None:
    key = _emb_cache_key(text)
    cached = _embedding_cache.get(key)
    if cached is not None:
        return cached
    # Try DB (single lookup — use _get_cached_embeddings_batch for many texts)
    try:
        from webapp.db import engine
        from sqlalchemy import text as sql_text
        with engine.connect() as conn:
            row = conn.execute(
                sql_text("SELECT embedding FROM embedding_cache WHERE cache_key = :k"),
                {"k": key},
            ).fetchone()
            if row:
                emb = _json.loads(row[0])
                _embedding_cache[key] = emb
                return emb
    except Exception:
        pass
    return None


def _get_cached_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """Fetch embeddings for multiple texts in ONE database round-trip.

    Returns a list parallel to `texts`: each element is the cached embedding
    or None if not found. Populates the in-memory cache for all hits.
    """
    if not texts:
        return []

    keys = [_emb_cache_key(t) for t in texts]
    results: list[list[float] | None] = [None] * len(texts)

    # Check in-memory cache first — no DB needed for already-loaded entries
    missing_indices = []
    for i, key in enumerate(keys):
        if key in _embedding_cache:
            results[i] = _embedding_cache[key]
        else:
            missing_indices.append(i)

    if not missing_indices:
        return results  # all in memory

    # One DB query for all missing keys
    try:
        from webapp.db import engine
        from sqlalchemy import text as sql_text
        missing_keys = [keys[i] for i in missing_indices]
        placeholders = ", ".join(f":k{j}" for j in range(len(missing_keys)))
        params = {f"k{j}": k for j, k in enumerate(missing_keys)}
        with engine.connect() as conn:
            rows = conn.execute(
                sql_text(
                    f"SELECT cache_key, embedding FROM embedding_cache "
                    f"WHERE cache_key IN ({placeholders})"
                ),
                params,
            ).fetchall()
        db_hits = {row[0]: _json.loads(row[1]) for row in rows}
        for i in missing_indices:
            emb = db_hits.get(keys[i])
            if emb is not None:
                _embedding_cache[keys[i]] = emb
                results[i] = emb
    except Exception:
        pass  # DB unavailable — caller will fall back to API

    return results


def _put_cached_embedding(text: str, embedding: list[float]) -> None:
    key = _emb_cache_key(text)
    _embedding_cache[key] = embedding
    try:
        from webapp.db import engine
        from sqlalchemy import text as sql_text
        with engine.connect() as conn:
            conn.execute(sql_text(
                "CREATE TABLE IF NOT EXISTS embedding_cache ("
                "  cache_key VARCHAR(64) PRIMARY KEY,"
                "  embedding TEXT NOT NULL,"
                "  created_at TIMESTAMP DEFAULT NOW()"
                ")"
            ))
            conn.execute(
                sql_text(
                    "INSERT INTO embedding_cache (cache_key, embedding) "
                    "VALUES (:k, :e) ON CONFLICT (cache_key) DO NOTHING"
                ),
                {"k": key, "e": _json.dumps(embedding)},
            )
            conn.commit()
    except Exception:
        pass


def clear_embedding_cache() -> None:
    """Clear the in-memory embedding cache (call at pipeline start)."""
    _embedding_cache.clear()


# ── Mock embeddings ─────────────────────────────────────

def _deterministic_embedding(text: str) -> list[float]:
    """Generate a deterministic pseudo-embedding from text content.
    Uses SHA-256 hash seeded PRNG so the same text always produces the
    same vector — making cosine similarity meaningful."""
    seed = int(hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(EMBEDDING_DIM)]
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec]


def mock_embed_text(text: str) -> list[float]:
    return _deterministic_embedding(text[:2000])


def mock_embed_texts(texts: list[str]) -> list[list[float]]:
    return [mock_embed_text(t) for t in texts]


# ── OpenAI embeddings ──────────────────────────────────
import os
import httpx
from openai import OpenAI

_openai_client = None

def _get_openai_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set. Add it to .env or environment variables.")
    # verify=True: always validate TLS certificates for the AI gateway.
    # Disable via OPENAI_SSL_VERIFY=false or TPRM_SSL_VERIFY=false (corporate proxy / dev only).
    _ssl_false = {"false", "0", "no"}
    _ssl_verify = (
        os.getenv("OPENAI_SSL_VERIFY", "true").lower() not in _ssl_false
        and os.getenv("TPRM_SSL_VERIFY", "true").lower() not in _ssl_false
    )
    _openai_client = OpenAI(api_key=key, http_client=httpx.Client(verify=_ssl_verify), base_url="https://ai.titan.in/gateway")
    return _openai_client

def openai_embed_text(text: str, model: str = "azure/text-embedding-3-small") -> list[float]:
    truncated = text[:8000]
    cached = _get_cached_embedding(truncated)
    if cached is not None:
        return cached
    client = _get_openai_client()
    try:
        response = client.embeddings.create(model="azure/text-embedding-3-small", input=truncated)
        emb = response.data[0].embedding
        _put_cached_embedding(truncated, emb)
        return emb
    except Exception as e:
        if "insufficient_quota" in str(e) or "429" in str(e) or "QUOTA" in str(e):
            raise RuntimeError(
                "Titan AI Gateway quota exceeded — your USD quota has been exhausted. "
                "Contact the AI Gateway admin to increase your quota "
                "or use Mock LLM mode."
            ) from e
        raise


def openai_embed_texts(texts: list[str], model: str = "azure/text-embedding-3-small",
                       batch_size: int = 100) -> list[list[float]]:
    client = _get_openai_client()
    all_embeddings = []
    # Check cache for each text; only call API for uncached ones
    truncated_texts = [t[:8000] for t in texts]
    results = [None] * len(truncated_texts)
    uncached_indices = []
    for i, t in enumerate(truncated_texts):
        cached = _get_cached_embedding(t)
        if cached is not None:
            results[i] = cached
        else:
            uncached_indices.append(i)

    if uncached_indices:
        uncached_texts = [truncated_texts[i] for i in uncached_indices]
        api_embeddings = []
        for i in range(0, len(uncached_texts), batch_size):
            batch = uncached_texts[i:i + batch_size]
            try:
                response = client.embeddings.create(model=model, input=batch)
                api_embeddings.extend([item.embedding for item in response.data])
                logger.info("Embedded batch %d: %d texts", i // batch_size + 1, len(batch))
            except Exception as e:
                if "insufficient_quota" in str(e) or "429" in str(e) or "QUOTA" in str(e):
                    raise RuntimeError(
                        "Titan AI Gateway quota exceeded — your USD quota has been exhausted. "
                        "Contact the AI Gateway admin to increase your quota "
                        "or use Mock LLM mode."
                    ) from e
                raise
        for idx, emb in zip(uncached_indices, api_embeddings):
            results[idx] = emb
            _put_cached_embedding(truncated_texts[idx], emb)

    return results


# ── Cosine similarity & search ─────────────────────────

def cosine_similarity(a, b) -> float:
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def similarity_search(query_embedding, records, embedding_key="embedding", top_k=5):
    """Rank records by cosine similarity using vectorised numpy ops.
    ~10-50x faster than the pure-Python loop for large chunk sets."""
    if not records:
        return []

    # Build matrix of all embeddings in one array
    valid = [(i, r) for i, r in enumerate(records) if r.get(embedding_key) is not None]
    if not valid:
        return []

    indices, recs = zip(*valid)
    mat = np.array([r[embedding_key] for r in recs], dtype=np.float32)  # (N, D)
    q   = np.array(query_embedding, dtype=np.float32)                   # (D,)

    # Cosine similarity via normalised dot products
    mat_norms = np.linalg.norm(mat, axis=1, keepdims=True)
    mat_norms[mat_norms == 0] = 1e-10
    q_norm = np.linalg.norm(q)
    if q_norm == 0:
        q_norm = 1e-10

    sims = (mat / mat_norms) @ (q / q_norm)  # (N,)

    # Stable sort — deterministic order for tied similarity scores.
    # Use a process-independent hash of the record ID as tiebreaker.
    import hashlib as _hl
    k = min(top_k, len(sims))
    _id_keys = np.array([
        int(_hl.sha256((r.get('id', '') or str(i)).encode()).hexdigest()[:15], 16)
        for i, r in enumerate(recs)
    ])
    order = np.lexsort((_id_keys, -sims))
    top_idx = order[:k]

    return [(float(sims[i]), recs[i]) for i in top_idx]
