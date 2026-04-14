import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.models import HITLFeedback
from app.schemas.schemas import HITLFeedbackCreate, HITLFeedbackResponse

router = APIRouter()


@router.post(
    "/feedback",
    response_model=HITLFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    body: HITLFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "analyst")),
):
    """Submit human-in-the-loop feedback on any entity."""
    feedback = HITLFeedback(
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        reviewer_id=user["user_id"],
        original_value=None,
        modified_value=body.modified_value,
        justification=body.justification,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback


@router.get("/feedback", response_model=list[HITLFeedbackResponse])
async def list_feedback(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "analyst")),
):
    """List HITL feedback entries with optional filters."""
    stmt = select(HITLFeedback)
    if entity_type:
        stmt = stmt.where(HITLFeedback.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(HITLFeedback.entity_id == entity_id)
    result = await db.execute(stmt)
    return result.scalars().all()
