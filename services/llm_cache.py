"""
LLM Response Cache
==================
Two-tier cache: in-memory (fast) + DB (persistent across runs).

HOW CACHE INVALIDATION WORKS — IMPORTANT:
==========================================
The cache key is SHA-256 of the FULL prompt text (system + user).

The gap analysis, recommendation, and risk prompts include the complete
questionnaire insights, retrieved evidence chunks, and policy context
verbatim. Therefore:

  - Same input files / answers  → identical prompt → same cache key
    → cached LLM response returned → consistent output every run

  - ANY change in questionnaire response, artifact, or policy
    → the prompt text changes → different SHA-256 → cache MISS
    → full fresh LLM call → new analysis reflects the change

The pipeline ALWAYS runs end-to-end (OCR, chunking, RAG retrieval,
pre-assessment scoring). Only the final LLM API call is short-circuited
when the assembled prompt is identical to a previous run.
This means runtime savings on repeat runs with unchanged input,
while guaranteeing full re-analysis whenever anything changes.
"""

import hashlib
import json as _json
import logging

logger = logging.getLogger("tprm.llm_cache")

# In-memory layer — fast lookups within and across runs (lives as long as the process)
_mem_cache: dict[str, dict] = {}


def _cache_key(prompt: str, system_prompt: str = "") -> str:
    """Compute a deterministic cache key from the full prompt pair."""
    combined = (system_prompt or "") + "\n---\n" + prompt
    return hashlib.sha256(combined.encode("utf-8", errors="replace")).hexdigest()


def _ensure_table(conn) -> None:
    from sqlalchemy import text as sql_text
    conn.execute(sql_text(
        "CREATE TABLE IF NOT EXISTS llm_cache ("
        "  cache_key   VARCHAR(64) PRIMARY KEY,"
        "  response    TEXT        NOT NULL,"
        "  created_at  TIMESTAMP   DEFAULT NOW()"
        ")"
    ))


def get_cached(prompt: str, system_prompt: str = "") -> dict | None:
    """Return cached LLM response (memory first, then DB), or None on miss."""
    key = _cache_key(prompt, system_prompt)

    # 1. Memory hit — fastest path
    if key in _mem_cache:
        logger.debug("LLM cache MEM-HIT  (key=%s…)", key[:12])
        return _mem_cache[key]

    # 2. DB hit — load into memory for subsequent calls
    try:
        from webapp.db import engine
        from sqlalchemy import text as sql_text
        with engine.connect() as conn:
            _ensure_table(conn)
            row = conn.execute(
                sql_text("SELECT response FROM llm_cache WHERE cache_key = :k"),
                {"k": key},
            ).fetchone()
            if row:
                response = _json.loads(row[0])
                _mem_cache[key] = response
                logger.info("LLM cache DB-HIT   (key=%s…) — skipping LLM API call", key[:12])
                return response
    except Exception as exc:
        logger.debug("LLM DB cache lookup failed: %s", exc)

    return None


def put_cached(prompt: str, system_prompt: str, response: dict) -> None:
    """Store LLM response in memory and persist to DB."""
    key = _cache_key(prompt, system_prompt)
    _mem_cache[key] = response

    try:
        from webapp.db import engine
        from sqlalchemy import text as sql_text
        with engine.connect() as conn:
            _ensure_table(conn)
            conn.execute(
                sql_text(
                    "INSERT INTO llm_cache (cache_key, response) "
                    "VALUES (:k, :r) ON CONFLICT (cache_key) DO NOTHING"
                ),
                {"k": key, "r": _json.dumps(response)},
            )
            conn.commit()
        logger.debug("LLM cache DB-STORE (key=%s…)", key[:12])
    except Exception as exc:
        logger.debug("LLM DB cache store failed (in-memory only): %s", exc)


def clear_cache() -> None:
    """Clear in-memory cache only. DB cache is intentionally preserved
    so that cross-run determinism is maintained."""
    _mem_cache.clear()


def clear_db_cache() -> None:
    """Wipe both memory and DB cache. Use only when you explicitly want
    to force a full re-analysis on all future runs (e.g. after a prompt change)."""
    _mem_cache.clear()
    try:
        from webapp.db import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM llm_cache"))
            conn.commit()
        logger.info("LLM DB cache fully cleared")
    except Exception:
        pass
