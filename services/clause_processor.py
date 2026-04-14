"""
Clause Processor Service
========================
Parses infosec contract clause DOCX files into individual clauses,
each with a unique ID and embedding.
"""

import logging
import re
import uuid
from pathlib import Path

from services.ocr_service import extract_text

# Namespace for deterministic UUID generation (same content → same ID every run)
_NS = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')

logger = logging.getLogger("tprm.clause_processor")


def process_clauses(clause_dir: Path, embed_fn) -> list[dict]:
    """
    Process contract clause files:
      1. Extract text
      2. Split into individual clauses
      3. Generate embedding per clause

    Returns list of clause dicts with:
      id, source_file, category, content, embedding
    """
    if not clause_dir.exists():
        logger.warning("Clause directory not found: %s", clause_dir)
        return []

    extensions = {".docx", ".pdf", ".txt"}
    files = sorted(f for f in clause_dir.iterdir()
                   if f.is_file() and f.suffix.lower() in extensions)

    clauses = []
    for cf in files:
        logger.info("Loading contract clauses: %s", cf.name)
        text = extract_text(str(cf))
        if not text.strip():
            logger.warning("No text extracted from %s — skipping", cf.name)
            continue

        # Split into individual clauses by numbered patterns or paragraph breaks
        raw_clauses = _split_into_clauses(text, cf.stem)

        for clause in raw_clauses:
            clause["embedding"] = embed_fn(clause["content"])
            clauses.append(clause)

        logger.info("  %s → %d clauses", cf.name, len(raw_clauses))

    return clauses


def _split_into_clauses(text: str, source_name: str) -> list[dict]:
    """Split contract text into individual clauses."""
    # Try numbered clause patterns first (e.g., "1.", "1.1", "Clause 1:")
    clause_pattern = re.compile(
        r'(?:^|\n)(?:\d+\.[\d.]*\s+|Clause\s+\d+[:\s])',
        re.MULTILINE | re.IGNORECASE,
    )
    matches = list(clause_pattern.finditer(text))

    if len(matches) >= 2:
        clauses = []
        for idx, m in enumerate(matches):
            start = m.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if content and len(content) > 20:
                clauses.append({
                    "id": str(uuid.uuid5(_NS, f"clause:{source_name}:{idx}:{content[:100]}")),
                    "source_file": source_name,
                    "category": source_name,
                    "content": content,
                })
        if clauses:
            return clauses

    # Fallback: split by double newlines (paragraphs)
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip() and len(p.strip()) > 20]
    if paragraphs:
        return [
            {
                "id": str(uuid.uuid5(_NS, f"clause:{source_name}:{i}:{p[:100]}")),
                "source_file": source_name,
                "category": source_name,
                "content": p,
            }
            for i, p in enumerate(paragraphs)
        ]

    # Last resort: treat entire text as one clause
    return [{
        "id": str(uuid.uuid5(_NS, f"clause:{source_name}:full:{text[:100]}")),
        "source_file": source_name,
        "category": source_name,
        "content": text,
    }]
