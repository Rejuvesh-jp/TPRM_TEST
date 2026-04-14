import logging
from app.core.config import get_settings

logger = logging.getLogger("tprm.chunking")
settings = get_settings()


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict]:
    """
    Split text into overlapping chunks using a sliding window approach.

    Returns a list of dicts: [{"index": 0, "content": "...", "char_start": 0, "char_end": 1000}, ...]
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    if not text or not text.strip():
        return []

    chunks = []
    start = 0
    index = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at a sentence or paragraph boundary
        if end < len(text):
            # Look for paragraph break
            para_break = text.rfind("\n\n", start + chunk_size // 2, end)
            if para_break != -1:
                end = para_break + 2
            else:
                # Look for sentence break
                sentence_break = text.rfind(". ", start + chunk_size // 2, end)
                if sentence_break != -1:
                    end = sentence_break + 2

        chunk_content = text[start:end].strip()
        if chunk_content:
            chunks.append({
                "index": index,
                "content": chunk_content,
                "char_start": start,
                "char_end": end,
            })
            index += 1

        start = end - chunk_overlap
        if start >= len(text):
            break

    logger.info(f"Chunked text into {len(chunks)} chunks (size={chunk_size}, overlap={chunk_overlap})")
    return chunks
