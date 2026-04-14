import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_api_key, require_role
from app.models.models import (
    Assessment, Vendor, Questionnaire, Question, Artifact,
    ArtifactInsight, GapAssessment, RiskAssessment, Recommendation,
    HITLFeedback,
)
from app.schemas.schemas import (
    VendorCreate, VendorResponse,
    AssessmentCreate, AssessmentResponse, AssessmentStatusResponse,
    AssessmentReport, GapResponse, RiskResponse, RecommendationResponse,
    TaskResponse, QuestionnaireResponse, QuestionResponse,
    ArtifactResponse, ArtifactInsightResponse, HITLFeedbackResponse,
)
from app.services.questionnaire_service import create_vendor, create_assessment
from app.workers.tasks import run_full_analysis_task

logger = logging.getLogger("tprm.api.assessments")

router = APIRouter()


# ─── Vendors ──────────────────────────────────────────────

@router.post("/vendors", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor_endpoint(
    body: VendorCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "analyst")),
):
    """Create a new vendor."""
    vendor = await create_vendor(db, body.name, body.domain)
    await db.commit()
    return vendor


@router.get("/vendors", response_model=list[VendorResponse])
async def list_vendors(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    """List all vendors."""
    result = await db.execute(select(Vendor))
    return result.scalars().all()


@router.get("/vendors/{vendor_id}", response_model=VendorResponse)
async def get_vendor(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor


# ─── Assessments ──────────────────────────────────────────

@router.post(
    "/assessments",
    response_model=AssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assessment_endpoint(
    body: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "analyst")),
):
    """Create a new assessment for a vendor."""
    vendor = await db.get(Vendor, body.vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    assessment = await create_assessment(db, body.vendor_id)
    await db.commit()
    return assessment


@router.get("/assessments", response_model=list[AssessmentResponse])
async def list_assessments(
    vendor_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    """List assessments, optionally filtered by vendor."""
    stmt = select(Assessment)
    if vendor_id:
        stmt = stmt.where(Assessment.vendor_id == vendor_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/assessments/{assessment_id}", response_model=AssessmentResponse)
async def get_assessment(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


@router.get("/assessments/{assessment_id}/status", response_model=AssessmentStatusResponse)
async def get_assessment_status(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    """Get current processing status of an assessment."""
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return AssessmentStatusResponse(
        id=assessment.id,
        status=assessment.status,
        stage=assessment.status,
        progress=None,
    )


# ─── Analysis Trigger ────────────────────────────────────

@router.post(
    "/assessments/{assessment_id}/analyze",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def trigger_analysis(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "analyst")),
):
    """Trigger full gap + risk + recommendation analysis pipeline."""
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    run_full_analysis_task(str(assessment_id))
    logger.info("Analysis pipeline completed for assessment %s", assessment_id)

    return TaskResponse(
        task_id=str(assessment_id),
        status="completed",
        message=f"Analysis pipeline completed for assessment {assessment_id}",
    )


# ─── Report ──────────────────────────────────────────────

@router.get("/assessments/{assessment_id}/report", response_model=AssessmentReport)
async def get_assessment_report(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    """Get the full assessment report aggregating all results."""
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    vendor = await db.get(Vendor, assessment.vendor_id)

    # Gather all related data
    questionnaires = (await db.execute(
        select(Questionnaire).where(Questionnaire.assessment_id == assessment_id)
    )).scalars().all()

    question_ids = [q.id for q in questionnaires]
    questions = []
    if question_ids:
        questions = (await db.execute(
            select(Question).where(Question.questionnaire_id.in_(question_ids))
        )).scalars().all()

    artifacts = (await db.execute(
        select(Artifact).where(Artifact.assessment_id == assessment_id)
    )).scalars().all()

    artifact_ids = [a.id for a in artifacts]
    insights = []
    if artifact_ids:
        insights = (await db.execute(
            select(ArtifactInsight).where(ArtifactInsight.artifact_id.in_(artifact_ids))
        )).scalars().all()

    gaps = (await db.execute(
        select(GapAssessment).where(GapAssessment.assessment_id == assessment_id)
    )).scalars().all()

    risks = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.assessment_id == assessment_id)
    )).scalars().all()

    risk_ids = [r.id for r in risks]
    recommendations = []
    if risk_ids:
        recommendations = (await db.execute(
            select(Recommendation).where(Recommendation.risk_assessment_id.in_(risk_ids))
        )).scalars().all()

    entity_ids = (
        [q.id for q in questionnaires]
        + [a.id for a in artifacts]
        + [g.id for g in gaps]
        + [r.id for r in risks]
    )
    feedback = []
    if entity_ids:
        feedback = (await db.execute(
            select(HITLFeedback).where(HITLFeedback.entity_id.in_(entity_ids))
        )).scalars().all()

    return AssessmentReport(
        assessment=assessment,
        vendor=vendor,
        questionnaire_insights=questionnaires,
        questions=questions,
        artifacts=artifacts,
        artifact_insights=insights,
        gaps=gaps,
        risks=risks,
        recommendations=recommendations,
        hitl_feedback=feedback,
    )


# ─── Gaps & Risks ────────────────────────────────────────

@router.get("/assessments/{assessment_id}/gaps", response_model=list[GapResponse])
async def list_gaps(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    result = await db.execute(
        select(GapAssessment).where(GapAssessment.assessment_id == assessment_id)
    )
    return result.scalars().all()


@router.get("/assessments/{assessment_id}/risks", response_model=list[RiskResponse])
async def list_risks(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    result = await db.execute(
        select(RiskAssessment).where(RiskAssessment.assessment_id == assessment_id)
    )
    return result.scalars().all()


@router.get(
    "/assessments/{assessment_id}/recommendations",
    response_model=list[RecommendationResponse],
)
async def list_recommendations(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    risks = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.assessment_id == assessment_id)
    )).scalars().all()
    risk_ids = [r.id for r in risks]
    if not risk_ids:
        return []
    result = await db.execute(
        select(Recommendation).where(Recommendation.risk_assessment_id.in_(risk_ids))
    )
    return result.scalars().all()
