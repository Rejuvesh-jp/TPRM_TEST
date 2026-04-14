"""
JSON Vector Store
=================
Stores and retrieves embedded document chunks in JSON files.
Provides cosine-similarity-based search without pgvector.
"""

import json
import logging
from pathlib import Path

from services.embedding_service import cosine_similarity

logger = logging.getLogger("tprm.vector_store")


class JsonVectorStore:
    """A JSON-file-backed vector store with cosine similarity search."""

    def __init__(self, store_dir: str | Path):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._stores: dict[str, list[dict]] = {}

    def _path(self, name: str) -> Path:
        return self.store_dir / f"{name}.json"

    def load(self, name: str) -> list[dict]:
        """Load a named vector store from disk."""
        path = self._path(name)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._stores[name] = data
            logger.info("Loaded vector store '%s': %d entries", name, len(data))
        else:
            self._stores[name] = []
        return self._stores[name]

    def save(self, name: str):
        """Persist a named vector store to disk."""
        data = self._stores.get(name, [])
        path = self._path(name)
        path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Saved vector store '%s': %d entries", name, len(data))

    def add(self, name: str, entry: dict):
        """Add an entry to a named store."""
        if name not in self._stores:
            self._stores[name] = []
        self._stores[name].append(entry)

    def add_many(self, name: str, entries: list[dict]):
        """Add multiple entries to a named store."""
        if name not in self._stores:
            self._stores[name] = []
        self._stores[name].extend(entries)

    def get_all(self, name: str) -> list[dict]:
        """Get all entries from a named store."""
        return self._stores.get(name, [])

    def search(self, name: str, query_embedding: list[float],
               embedding_key: str = "embedding", top_k: int = 5) -> list[tuple[float, dict]]:
        """Search a named store by cosine similarity."""
        records = self._stores.get(name, [])
        scored = []
        for rec in records:
            emb = rec.get(embedding_key)
            if emb is None:
                continue
            sim = cosine_similarity(query_embedding, emb)
            scored.append((sim, rec))
        scored.sort(key=lambda x: (-x[0], x[1].get('id', '')))
        return scored[:top_k]

    def count(self, name: str) -> int:
        return len(self._stores.get(name, []))
