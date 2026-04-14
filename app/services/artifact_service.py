import json
import logging
import uuid
import zipfile
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.models import Artifact, ArtifactChunk, ArtifactInsight
from app.utils.extraction import extract_text, extract_text_from_bytes, EXTRACTORS
from app.utils.chunking import chunk_text
from app.services.embedding_service import embed_texts
from app.utils.llm import call_llm_json
from app.utils.prompts import render_prompt, get_system_prompt
from app.core.config import get_settings

logger = logging.getLogger("tprm.artifact_service")
settings = get_settings()


def process_artifact_sync(artifact_id: str, db: Session):
    """Full artifact processing pipeline: extract -> chunk -> embed -> insight (sync)."""
    artifact = db.query(Artifact).filter(Artifact.id == uuid.UUID(artifact_id)).first()
    if not artifact:
        raise ValueError(f"Artifact {artifact_id} not found")

    try:
        artifact.processing_status = "extracted"
        db.commit()

        file_path = Path(artifact.file_path)

        # Handle ZIP archives
        if file_path.suffix.lower() == ".zip":
            _process_zip_archive(artifact, file_path, db)
            return

        # Extract text
        text = extract_text(str(file_path))
        if not text.strip():
            artifact.processing_status = "failed"
            artifact.error_log = "No text could be extracted from file"
            db.commit()
            return

        # Chunk
        artifact.processing_status = "chunked"
        db.commit()
        chunks = chunk_text(text)

        # Embed
        chunk_texts = [c["content"] for c in chunks]
        embeddings = embed_texts(chunk_texts)

        artifact.processing_status = "embedded"
        db.commit()

        # Store chunks with embeddings
        for chunk_data, embedding in zip(chunks, embeddings):
            chunk = ArtifactChunk(
                artifact_id=artifact.id,
                chunk_index=chunk_data["index"],
                content=chunk_data["content"],
                embedding=embedding,
                metadata_={
                    "char_start": chunk_data["char_start"],
                    "char_end": chunk_data["char_end"],
                },
            )
            db.add(chunk)

        db.commit()

        # Generate insights
        _generate_artifact_insights(artifact, text, db)

        artifact.processing_status = "analyzed"
        db.commit()
        logger.info(f"Processed artifact {artifact_id}: {len(chunks)} chunks")

    except Exception as e:
        artifact.processing_status = "failed"
        artifact.error_log = str(e)
        db.commit()
        logger.error(f"Failed to process artifact {artifact_id}: {e}")
        raise


def _process_zip_archive(artifact: Artifact, zip_path: Path, db: Session):
    """Extract and process files from a ZIP archive."""
    extract_dir = Path(settings.UPLOAD_DIR) / str(artifact.assessment_id) / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    allowed_extensions = set(EXTRACTORS.keys())

    with zipfile.ZipFile(str(zip_path), "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            ext = Path(info.filename).suffix.lower()
            if ext == ".zip":
                logger.warning(f"Skipping nested ZIP: {info.filename}")
                continue
            if ext not in allowed_extensions:
                logger.warning(f"Skipping unsupported file: {info.filename}")
                continue

            # Extract file — use only the basename to prevent Zip Slip path traversal
            safe_name = Path(info.filename).name
            if not safe_name or safe_name.startswith("."):
                logger.warning("Skipping suspicious zip entry: %s", info.filename)
                continue
            extracted_path = (extract_dir / safe_name).resolve()
            if not str(extracted_path).startswith(str(extract_dir.resolve())):
                logger.warning("Zip Slip blocked: %s", info.filename)
                continue
            with zf.open(info) as source, open(extracted_path, "wb") as target:
                target.write(source.read())

            # Create a child artifact for each file
            child = Artifact(
                assessment_id=artifact.assessment_id,
                file_name=info.filename,
                file_path=str(extracted_path),
                file_type=ext,
                file_size=info.file_size,
                processing_status="uploaded",
            )
            db.add(child)
            db.flush()

            # Process the child
            process_artifact_sync(str(child.id), db)

    artifact.processing_status = "analyzed"
    db.commit()


def _generate_artifact_insights(artifact: Artifact, text: str, db: Session):
    """Generate AI insights from artifact content."""
    prompt = render_prompt(
        "artifact_insight",
        artifact_name=artifact.file_name,
        artifact_content=text[:12000],
    )
    system = get_system_prompt("artifact_insight")
    insights_data = call_llm_json(prompt=prompt, system_prompt=system)

    # Store structured insights
    insight_types = [
        ("policy_coverage", insights_data.get("policy_coverage", [])),
        ("certifications", insights_data.get("certifications", [])),
        ("compliance_indicators", insights_data.get("compliance_indicators", [])),
    ]

    for insight_type, items in insight_types:
        if items:
            insight = ArtifactInsight(
                artifact_id=artifact.id,
                insight_type=insight_type,
                description=json.dumps(items),
                confidence=insights_data.get("confidence"),
            )
            db.add(insight)

    for control in insights_data.get("security_controls", []):
        insight = ArtifactInsight(
            artifact_id=artifact.id,
            insight_type="control",
            description=json.dumps(control),
            confidence=insights_data.get("confidence"),
        )
        db.add(insight)

    for finding in insights_data.get("key_findings", []):
        insight = ArtifactInsight(
            artifact_id=artifact.id,
            insight_type="key_finding",
            description=finding,
            confidence=insights_data.get("confidence"),
        )
        db.add(insight)

    db.commit()
