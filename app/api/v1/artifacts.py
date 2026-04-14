import logging
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import verify_api_key, require_role
from app.models.models import Artifact, ArtifactInsight, Assessment
from app.schemas.schemas import ArtifactResponse, ArtifactInsightResponse, TaskResponse
from app.workers.tasks import process_artifact_task

logger = logging.getLogger("tprm.api.artifacts")

settings = get_settings()
router = APIRouter()

UPLOAD_DIR = Path(settings.UPLOAD_DIR) / "artifacts"
ALLOWED_EXTENSIONS = set(settings.ALLOWED_EXTENSIONS + [".zip"])


@router.post(
    "/assessments/{assessment_id}/artifacts",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_artifact(
    assessment_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "analyst")),
):
    """Upload a vendor artifact for processing."""
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / f"{uuid.uuid4()}{ext}"
    file_path.write_bytes(content)

    artifact = Artifact(
        assessment_id=assessment_id,
        file_name=file.filename or f"artifact{ext}",
        file_path=str(file_path),
        file_type=ext.lstrip("."),
        file_size=len(content),
        processing_status="uploaded",
    )
    db.add(artifact)
    await db.flush()
    await db.commit()

    process_artifact_task(str(artifact.id))
    logger.info("Artifact %s processed successfully", artifact.id)

    return TaskResponse(
        task_id=str(artifact.id),
        status="completed",
        message=f"Artifact {artifact.id} processed successfully",
    )


@router.get(
    "/assessments/{assessment_id}/artifacts",
    response_model=list[ArtifactResponse],
)
async def list_artifacts(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    """List artifacts for an assessment."""
    result = await db.execute(
        select(Artifact).where(Artifact.assessment_id == assessment_id)
    )
    return result.scalars().all()


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    """Get artifact details."""
    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.get(
    "/artifacts/{artifact_id}/insights",
    response_model=list[ArtifactInsightResponse],
)
async def list_artifact_insights(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    """List insights extracted from an artifact."""
    result = await db.execute(
        select(ArtifactInsight).where(ArtifactInsight.artifact_id == artifact_id)
    )
    return result.scalars().all()
