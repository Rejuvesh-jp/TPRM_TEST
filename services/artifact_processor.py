"""
Artifact Processor Service
==========================
Processes vendor artifact files: extracts text, chunks, generates embeddings,
and produces per-artifact insights.

Performance: artifact files are processed in parallel using ThreadPoolExecutor.
Each file's extraction, chunking, embedding, and LLM insight call run
concurrently — dramatically reducing wall-clock time for multi-file uploads.
"""

import logging
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Namespace for deterministic UUID generation (same content → same ID every run)
_NS = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')

from services.ocr_service import extract_text, SUPPORTED_EXTENSIONS

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_MAX_WORKERS = 4  # concurrent artifact LLM calls; tune to gateway rate-limit

logger = logging.getLogger("tprm.artifact_processor")


def extract_zip(zip_path: str | Path, dest_dir: str | Path) -> list[Path]:
    """Extract a ZIP file and return list of extracted file paths."""
    zip_path = Path(zip_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    extracted = []
    with zipfile.ZipFile(str(zip_path), 'r') as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            ext = Path(info.filename).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            # Zip Slip prevention: resolve and verify path stays inside dest_dir
            target_path = (dest_dir / info.filename).resolve()
            if not str(target_path).startswith(str(dest_dir.resolve())):
                logger.warning("Zip Slip blocked: %s", info.filename)
                continue
            zf.extract(info, str(dest_dir))
            extracted.append(dest_dir / info.filename)
    logger.info("Extracted %d files from %s", len(extracted), zip_path.name)
    return sorted(extracted)


def discover_files(folder: Path, extensions: set[str] | None = None) -> list[Path]:
    """List files in folder matching given extensions (case-insensitive)."""
    if not folder.exists():
        return []
    files = sorted(f for f in folder.iterdir() if f.is_file())
    if extensions:
        files = [f for f in files if f.suffix.lower() in extensions]
    return files


def _process_single_artifact(af: Path, chunk_fn, embed_fn, embed_batch_fn,
                              llm_fn, render_prompt_fn, get_system_prompt_fn) -> dict | None:
    """Process one artifact file: extract → chunk → embed → LLM insight.
    Returns artifact dict or None if file is skipped."""
    t_start = time.perf_counter()
    is_image = af.suffix.lower() in IMAGE_EXTENSIONS

    # ── Text extraction ──────────────────────────────────────
    t_ocr = time.perf_counter()
    try:
        text = extract_text(str(af))
    except Exception as exc:
        logger.warning("Could not extract text from %s: %s", af.name, exc)
        text = ""
    ocr_ms = (time.perf_counter() - t_ocr) * 1000

    if is_image:
        fname_context = af.stem.replace("_", " ").replace("-", " ")
        if text.strip():
            text = (
                f"[Image artifact: {af.name}]\n"
                f"[Filename context: {fname_context}]\n\n"
                f"OCR-extracted text:\n{text}"
            )
        else:
            text = (
                f"[Image artifact: {af.name}]\n"
                f"[Filename context: {fname_context}]\n\n"
                f"This is an image file provided as supporting evidence. "
                f"The filename suggests it relates to: {fname_context}."
            )

    if not text.strip():
        logger.warning("No text in %s — skipping", af.name)
        return None

    # ── Chunking + batch embedding ───────────────────────────
    t_embed = time.perf_counter()
    chunks_raw = chunk_fn(text)
    chunk_texts = [c["content"] for c in chunks_raw]
    embeddings = embed_batch_fn(chunk_texts)
    file_embedding = embed_fn(text[:8000])
    embed_ms = (time.perf_counter() - t_embed) * 1000

    chunks = []
    for cd, emb in zip(chunks_raw, embeddings):
        chunks.append({
            "id": str(uuid.uuid5(_NS, f"chunk:{af.name}:{cd['index']}")),
            "chunk_index": cd["index"],
            "content": cd["content"],
            "embedding": emb,
            "metadata": {"char_start": cd["char_start"], "char_end": cd["char_end"]},
        })

    logger.debug(
        "Artifact %s: %d chunks, IDs=%s",
        af.name, len(chunks), [c["id"][:12] for c in chunks],
    )

    # ── LLM insight ─────────────────────────────────────────
    t_llm = time.perf_counter()
    insight_prompt = render_prompt_fn(
        "artifact_insight",
        artifact_name=af.name,
        artifact_content=text[:12000],
        source_type="image (OCR-extracted)" if is_image else "document",
    )
    insight_data = llm_fn(
        insight_prompt,
        system_prompt=get_system_prompt_fn("artifact_insight"),
        max_tokens=4096,
    )
    llm_ms = (time.perf_counter() - t_llm) * 1000

    total_ms = (time.perf_counter() - t_start) * 1000
    logger.info(
        "[PERF] artifact=%s  ocr=%.0fms  embed=%.0fms  llm=%.0fms  total=%.0fms  chunks=%d",
        af.name, ocr_ms, embed_ms, llm_ms, total_ms, len(chunks)
    )

    return {
        "id": str(uuid.uuid5(_NS, f"artifact:{af.name}")),
        "file_name": af.name,
        "source_type": "image" if is_image else "document",
        "file_embedding": file_embedding,
        "chunks": chunks,
        "insights": insight_data,
    }


def process_artifacts(artifact_dir: Path, chunk_fn, embed_fn, embed_batch_fn,
                      llm_fn, render_prompt_fn, get_system_prompt_fn,
                      max_artifacts: int | None = None) -> list[dict]:
    """
    Process all artifact files in a directory IN PARALLEL.
    Workers == min(_MAX_WORKERS, n_files) so small uploads don't over-thread.
    """
    files = discover_files(artifact_dir, SUPPORTED_EXTENSIONS)

    zip_files = discover_files(artifact_dir, {".zip"})
    for zf in zip_files:
        extracted = extract_zip(zf, artifact_dir / "_extracted")
        files.extend(extracted)

    if max_artifacts and len(files) > max_artifacts:
        logger.info("Limiting to %d artifacts (of %d)", max_artifacts, len(files))
        files = files[:max_artifacts]

    if not files:
        logger.info("No artifact files found")
        return []

    n_workers = min(_MAX_WORKERS, len(files))
    logger.info("[PERF] Processing %d artifact(s) with %d parallel worker(s)", len(files), n_workers)
    t0 = time.perf_counter()

    artifacts: list[dict] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(
                _process_single_artifact, af,
                chunk_fn, embed_fn, embed_batch_fn,
                llm_fn, render_prompt_fn, get_system_prompt_fn
            ): af.name
            for af in files
        }
        for future in as_completed(futures):
            fname = futures[future]
            try:
                result = future.result()
                if result is not None:
                    artifacts.append(result)
            except Exception as exc:
                logger.error("[PERF] Artifact %s failed: %s", fname, exc)
                errors.append(fname)

    # Stable ordering for deterministic downstream behaviour
    artifacts.sort(key=lambda a: a["file_name"])
    total_chunks = sum(len(a["chunks"]) for a in artifacts)
    wall_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "[PERF] artifact_processor done: %d/%d ok, %d skipped/failed, "
        "%d total chunks, wall=%.0fms",
        len(artifacts), len(files), len(errors), total_chunks, wall_ms
    )
    return artifacts
