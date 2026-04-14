"""
Policy Processor Service
========================
Processes TPRM policy PDFs (with OCR fallback) and infosec contract
clause DOCX files. Chunks and embeds for vector store storage.
"""

import logging
import uuid
from pathlib import Path

from services.ocr_service import extract_text

# Namespace for deterministic UUID generation (same content → same ID every run)
_NS = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')

logger = logging.getLogger("tprm.policy_processor")


def process_policies(policy_dir: Path, chunk_fn, embed_fn) -> list[dict]:
    """
    Process policy files:
      1. Extract text (OCR if scanned)
      2. Chunk intelligently
      3. Generate embeddings per chunk + file-level embedding

    Returns list of policy dicts with:
      id, title, content, file_embedding, chunks[]
    """
    if not policy_dir.exists():
        logger.warning("Policy directory not found: %s", policy_dir)
        return []

    extensions = {".pdf", ".txt", ".docx"}
    files = sorted(f for f in policy_dir.iterdir()
                   if f.is_file() and f.suffix.lower() in extensions)

    policies = []
    for pf in files:
        logger.info("Loading policy: %s", pf.name)
        text = extract_text(str(pf))
        if not text.strip():
            logger.warning("No text extracted from %s (may be scanned) — skipping", pf.name)
            continue

        # Chunk the policy
        chunks_raw = chunk_fn(text)
        chunks = []
        for c in chunks_raw:
            chunks.append({
                "id": str(uuid.uuid5(_NS, f"polchunk:{pf.name}:{c['index']}")),
                "chunk_index": c["index"],
                "content": c["content"],
                "embedding": embed_fn(c["content"]),
                "metadata": {"char_start": c["char_start"], "char_end": c["char_end"]},
            })

        file_embedding = embed_fn(text[:8000])

        policies.append({
            "id": str(uuid.uuid5(_NS, f"policy:{pf.name}")),
            "title": pf.stem,
            "content": text,
            "file_embedding": file_embedding,
            "chunks": chunks,
        })
        logger.info("  %s → %d chunks", pf.name, len(chunks))

    return policies
