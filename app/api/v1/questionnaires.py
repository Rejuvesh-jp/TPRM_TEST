import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import verify_api_key, require_role
from app.models.models import Questionnaire, Question, Assessment
from app.schemas.schemas import (
    QuestionnaireResponse, QuestionResponse, TaskResponse,
)
from app.services.questionnaire_service import store_questionnaire
from app.workers.tasks import parse_questionnaire_task

logger = logging.getLogger("tprm.api.questionnaires")

settings = get_settings()
router = APIRouter()

UPLOAD_DIR = Path(settings.UPLOAD_DIR) / "questionnaires"


@router.post(
    "/assessments/{assessment_id}/questionnaires",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_questionnaire(
    assessment_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "analyst")),
):
    """Upload a SIG Lite questionnaire for analysis."""
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".pdf",):
        raise HTTPException(status_code=400, detail="Only PDF questionnaires are supported")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / f"{uuid.uuid4()}{ext}"
    content = await file.read()
    file_path.write_bytes(content)

    questionnaire = await store_questionnaire(
        db, assessment_id, file.filename or "questionnaire.pdf",
        str(file_path), len(content),
    )
    await db.commit()

    parse_questionnaire_task(str(questionnaire.id))
    logger.info("Questionnaire %s processed successfully", questionnaire.id)

    return TaskResponse(
        task_id=str(questionnaire.id),
        status="completed",
        message=f"Questionnaire {questionnaire.id} processed successfully",
    )


@router.get(
    "/assessments/{assessment_id}/questionnaires",
    response_model=list[QuestionnaireResponse],
)
async def list_questionnaires(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    """List questionnaires for an assessment."""
    result = await db.execute(
        select(Questionnaire).where(Questionnaire.assessment_id == assessment_id)
    )
    return result.scalars().all()


@router.get(
    "/questionnaires/{questionnaire_id}",
    response_model=QuestionnaireResponse,
)
async def get_questionnaire(
    questionnaire_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    """Get questionnaire details and analysis results."""
    q = await db.get(Questionnaire, questionnaire_id)
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    return q


@router.get(
    "/questionnaires/{questionnaire_id}/questions",
    response_model=list[QuestionResponse],
)
async def list_questions(
    questionnaire_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    """List parsed questions from a questionnaire."""
    result = await db.execute(
        select(Question).where(Question.questionnaire_id == questionnaire_id)
    )
    return result.scalars().all()
