import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_api_key, require_role
from app.models.models import Policy, ContractClause
from app.schemas.schemas import (
    PolicyCreate, PolicyResponse, ContractClauseCreate, ContractClauseResponse,
)
from app.services.embedding_service import embed_text
from app.utils.extraction import extract_text_from_bytes

router = APIRouter()


# ─── Policies ─────────────────────────────────────────────

@router.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    title: str = Form(...),
    file: UploadFile = File(...),
    version: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Upload an internal policy document."""
    content_bytes = await file.read()
    ext = Path(file.filename or "policy.txt").suffix.lower()
    text = extract_text_from_bytes(content_bytes, ext)
    embedding = embed_text(text[:8000])

    policy = Policy(
        title=title,
        version=version,
        content=text,
        embedding=embedding,
        active=True,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("/policies", response_model=list[PolicyResponse])
async def list_policies(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    result = await db.execute(select(Policy).where(Policy.active == True))
    return result.scalars().all()


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_policy(
    policy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Soft-delete a policy by marking it inactive."""
    policy = await db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy.active = False
    await db.commit()


# ─── Contract Clauses ────────────────────────────────────

@router.post(
    "/contract-clauses",
    response_model=ContractClauseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract_clause(
    category: str = Form(...),
    file: UploadFile = File(...),
    standard_clause: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Upload a contract clause document."""
    content_bytes = await file.read()
    ext = Path(file.filename or "clause.txt").suffix.lower()
    text = extract_text_from_bytes(content_bytes, ext)
    embedding = embed_text(text[:8000])

    clause = ContractClause(
        category=category,
        content=text,
        embedding=embedding,
        standard_clause=standard_clause,
    )
    db.add(clause)
    await db.commit()
    await db.refresh(clause)
    return clause


@router.get("/contract-clauses", response_model=list[ContractClauseResponse])
async def list_contract_clauses(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(verify_api_key),
):
    result = await db.execute(select(ContractClause))
    return result.scalars().all()
