"""
Retrieval service — semantic similarity search over JSONB-stored embeddings.

Cosine similarity is computed in Python with numpy.  When pgvector is available
later, swap this module to use the <=> operator for in-database search.
"""

import logging

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.models import Artifact, ArtifactChunk, Policy, ContractClause
from app.services.embedding_service import embed_text

logger = logging.getLogger("tprm.retrieval_service")


# ── helper ───────────────────────────────────────────────────────────
def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors (returns 0.0–1.0)."""
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def _rank_by_similarity(
    query_vec: np.ndarray,
    rows: list[tuple],
    embedding_idx: int,
    top_k: int,
) -> list[tuple[float, tuple]]:
    """Score *rows* against *query_vec* and return top-k (highest similarity first).

    Each entry in the returned list is ``(similarity, row_tuple)``.
    """
    scored = []
    for row in rows:
        emb = row[embedding_idx]
        if emb is None:
            continue
        sim = _cosine_similarity(query_vec, np.asarray(emb, dtype=np.float32))
        scored.append((sim, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


# ── Artifact chunks ─────────────────────────────────────────────────

async def search_artifact_chunks(
    db: AsyncSession,
    query: str,
    assessment_id: str,
    top_k: int = 10,
) -> list[dict]:
    """Search artifact chunks by cosine similarity within an assessment."""
    query_vec = np.asarray(embed_text(query), dtype=np.float32)
    logger.info("Running Python cosine similarity search (pgvector fallback)")

    stmt = (
        select(ArtifactChunk.id, ArtifactChunk.content, ArtifactChunk.metadata_, ArtifactChunk.embedding)
        .join(Artifact, ArtifactChunk.artifact_id == Artifact.id)
        .where(Artifact.assessment_id == assessment_id)
        .where(ArtifactChunk.embedding.isnot(None))
        .limit(2000)
    )
    result = await db.execute(stmt)
    rows = result.all()

    ranked = _rank_by_similarity(query_vec, rows, embedding_idx=3, top_k=top_k)
    return [
        {"id": str(r[0]), "content": r[1], "metadata": r[2], "distance": round(1 - sim, 6)}
        for sim, r in ranked
    ]


async def search_policies(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """Search active policies by cosine similarity."""
    query_vec = np.asarray(embed_text(query), dtype=np.float32)
    logger.info("Running Python cosine similarity search (pgvector fallback)")

    stmt = (
        select(Policy.id, Policy.title, Policy.content, Policy.embedding)
        .where(Policy.active == True, Policy.embedding.isnot(None))  # noqa: E712
        .limit(2000)
    )
    result = await db.execute(stmt)
    rows = result.all()

    ranked = _rank_by_similarity(query_vec, rows, embedding_idx=3, top_k=top_k)
    return [
        {"id": str(r[0]), "title": r[1], "content": r[2], "distance": round(1 - sim, 6)}
        for sim, r in ranked
    ]


async def search_contract_clauses(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """Search contract clauses by cosine similarity."""
    query_vec = np.asarray(embed_text(query), dtype=np.float32)
    logger.info("Running Python cosine similarity search (pgvector fallback)")

    stmt = (
        select(ContractClause.id, ContractClause.category, ContractClause.content, ContractClause.embedding)
        .where(ContractClause.embedding.isnot(None))
        .limit(2000)
    )
    result = await db.execute(stmt)
    rows = result.all()

    ranked = _rank_by_similarity(query_vec, rows, embedding_idx=3, top_k=top_k)
    return [
        {"id": str(r[0]), "category": r[1], "content": r[2], "distance": round(1 - sim, 6)}
        for sim, r in ranked
    ]


# ── Sync variants ──────────────────────────────────────────

def search_artifact_chunks_sync(
    db: Session,
    query: str,
    assessment_id: str,
    top_k: int = 10,
) -> list[dict]:
    """Sync cosine-similarity search over artifact chunks."""
    query_vec = np.asarray(embed_text(query), dtype=np.float32)
    logger.info("Running Python cosine similarity search (pgvector fallback)")

    stmt = (
        select(ArtifactChunk.id, ArtifactChunk.content, ArtifactChunk.metadata_, ArtifactChunk.embedding)
        .join(Artifact, ArtifactChunk.artifact_id == Artifact.id)
        .where(Artifact.assessment_id == assessment_id)
        .where(ArtifactChunk.embedding.isnot(None))
        .limit(2000)
    )
    rows = db.execute(stmt).all()

    ranked = _rank_by_similarity(query_vec, rows, embedding_idx=3, top_k=top_k)
    return [
        {"id": str(r[0]), "content": r[1], "metadata": r[2], "distance": round(1 - sim, 6)}
        for sim, r in ranked
    ]


def search_policies_sync(db: Session, query: str, top_k: int = 5) -> list[dict]:
    """Sync cosine-similarity search over policies."""
    query_vec = np.asarray(embed_text(query), dtype=np.float32)
    logger.info("Running Python cosine similarity search (pgvector fallback)")

    stmt = (
        select(Policy.id, Policy.title, Policy.content, Policy.embedding)
        .where(Policy.active == True, Policy.embedding.isnot(None))  # noqa: E712
        .limit(2000)
    )
    rows = db.execute(stmt).all()

    ranked = _rank_by_similarity(query_vec, rows, embedding_idx=3, top_k=top_k)
    return [
        {"id": str(r[0]), "title": r[1], "content": r[2], "distance": round(1 - sim, 6)}
        for sim, r in ranked
    ]


def search_contract_clauses_sync(db: Session, query: str, top_k: int = 5) -> list[dict]:
    """Sync cosine-similarity search over contract clauses."""
    query_vec = np.asarray(embed_text(query), dtype=np.float32)
    logger.info("Running Python cosine similarity search (pgvector fallback)")

    stmt = (
        select(ContractClause.id, ContractClause.category, ContractClause.content, ContractClause.embedding)
        .where(ContractClause.embedding.isnot(None))
        .limit(2000)
    )
    rows = db.execute(stmt).all()

    ranked = _rank_by_similarity(query_vec, rows, embedding_idx=3, top_k=top_k)
    return [
        {"id": str(r[0]), "category": r[1], "content": r[2], "distance": round(1 - sim, 6)}
        for sim, r in ranked
    ]
