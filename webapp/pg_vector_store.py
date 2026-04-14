"""
pgvector Vector Store
=====================
PostgreSQL + pgvector backed vector store, replacing JsonVectorStore.
Stores embeddings in the embeddings table and uses cosine distance for search.
"""
import logging

from sqlalchemy import select, text, func

from webapp.db import get_session
from webapp.models import Embedding

logger = logging.getLogger("tprm.pg_vector_store")


class PgVectorStore:
    """PostgreSQL + pgvector backed vector store."""

    def __init__(self, assessment_id: str):
        self.assessment_id = assessment_id
        self._buffer: dict[str, list[dict]] = {}

    def add(self, store_name: str, entry: dict):
        """Buffer an entry for later batch save."""
        if store_name not in self._buffer:
            self._buffer[store_name] = []
        self._buffer[store_name].append(entry)

    def add_many(self, store_name: str, entries: list[dict]):
        """Buffer multiple entries for later batch save."""
        if store_name not in self._buffer:
            self._buffer[store_name] = []
        self._buffer[store_name].extend(entries)

    def save(self, store_name: str):
        """Flush buffered entries for a store to the database using a bulk insert."""
        entries = self._buffer.get(store_name, [])
        if not entries:
            return

        with get_session() as session:
            objects = [
                Embedding(
                    assessment_id=self.assessment_id,
                    store_name=store_name,
                    chunk_id=entry.get("chunk_id", ""),
                    source_document=entry.get("source_document"),
                    chunk_text=entry.get("chunk_text"),
                    embedding=entry.get("embedding"),
                )
                for entry in entries
            ]
            session.bulk_save_objects(objects)
            session.commit()

        count = len(entries)
        self._buffer[store_name] = []
        logger.info("Saved %d vectors to '%s' for assessment %s", count, store_name, self.assessment_id[:8])

    def get_all(self, store_name: str) -> list[dict]:
        """Get all entries from a store (returns dicts with embedding lists)."""
        with get_session() as session:
            stmt = (
                select(Embedding)
                .where(
                    Embedding.assessment_id == self.assessment_id,
                    Embedding.store_name == store_name,
                )
                .order_by(Embedding.chunk_id)
            )
            rows = session.scalars(stmt).all()
            return [
                {
                    "chunk_id": r.chunk_id,
                    "source_document": r.source_document,
                    "chunk_text": r.chunk_text,
                    "embedding": list(r.embedding) if r.embedding is not None else None,
                }
                for r in rows
            ]

    def search(self, store_name: str, query_embedding: list[float],
               top_k: int = 5) -> list[tuple[float, dict]]:
        """Search by cosine similarity using pgvector <=> operator."""
        with get_session() as session:
            # pgvector cosine distance: <=> returns distance (0=identical, 2=opposite)
            # similarity = 1 - distance
            distance = Embedding.embedding.cosine_distance(query_embedding)
            stmt = (
                select(Embedding, distance.label("distance"))
                .where(
                    Embedding.assessment_id == self.assessment_id,
                    Embedding.store_name == store_name,
                    Embedding.embedding.isnot(None),
                )
                .order_by(distance, Embedding.chunk_id)
                .limit(top_k)
            )
            results = session.execute(stmt).all()
            return [
                (
                    1.0 - float(row.distance),  # convert distance to similarity
                    {
                        "chunk_id": row.Embedding.chunk_id,
                        "source_document": row.Embedding.source_document,
                        "chunk_text": row.Embedding.chunk_text,
                        "embedding": list(row.Embedding.embedding) if row.Embedding.embedding is not None else None,
                    },
                )
                for row in results
            ]

    def count(self, store_name: str) -> int:
        """Count entries in a store."""
        with get_session() as session:
            stmt = (
                select(func.count())
                .select_from(Embedding)
                .where(
                    Embedding.assessment_id == self.assessment_id,
                    Embedding.store_name == store_name,
                )
            )
            return session.scalar(stmt) or 0
