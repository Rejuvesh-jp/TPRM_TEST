import logging
from app.utils.llm import generate_embedding, generate_embeddings_batch

logger = logging.getLogger("tprm.embedding_service")


def embed_text(text: str) -> list[float]:
    """Generate embedding for a single text."""
    return generate_embedding(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts in batches."""
    return generate_embeddings_batch(texts)
