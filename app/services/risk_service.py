import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import (
    Assessment, GapAssessment, RiskAssessment, Recommendation, Vendor,
)
from app.services.retrieval_service import search_contract_clauses_sync
from app.utils.llm import call_llm_json
from app.utils.prompts import render_prompt, get_system_prompt

logger = logging.getLogger("tprm.risk_service")


def run_risk_assessment_sync(
    db: Session, assessment_id: uuid.UUID
) -> list[RiskAssessment]:
    """Score gaps into risk levels (sync)."""

    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise ValueError(f"Assessment {assessment_id} not found")

    vendor = db.get(Vendor, assessment.vendor_id)

    gaps = db.execute(
        select(GapAssessment).where(GapAssessment.assessment_id == assessment_id)
    ).scalars().all()

    if not gaps:
        logger.info("No gaps found for assessment %s, skipping risk scoring", assessment_id)
        return []

    gaps_data = json.dumps([
        {
            "gap_id": str(g.id),
            "gap_type": g.gap_type,
            "description": g.description,
            "severity": g.severity,
            "source_refs": g.source_refs,
        }
        for g in gaps
    ], indent=2)

    vendor_context = json.dumps({
        "vendor_name": vendor.name if vendor else "Unknown",
        "vendor_domain": vendor.domain if vendor else None,
    })

    user_prompt = render_prompt("risk_assessment", {
        "gaps_data": gaps_data,
        "vendor_context": vendor_context,
    })
    system_prompt = get_system_prompt("risk_assessment")

    result = call_llm_json(user_prompt, system_prompt=system_prompt)

    # Store risk assessments
    gap_id_map = {str(g.id): g.id for g in gaps}
    risks_created = []

    for score in result.get("risk_scores", []):
        gap_uuid_str = score.get("gap_id", "")
        if gap_uuid_str not in gap_id_map:
            logger.warning("Unknown gap_id %s in risk response, skipping", gap_uuid_str)
            continue

        risk = RiskAssessment(
            assessment_id=assessment_id,
            gap_id=gap_id_map[gap_uuid_str],
            risk_level=score.get("risk_level", "medium"),
            rationale=score.get("rationale", ""),
            remediation_plan=score.get("remediation_plan"),
            status="open",
        )
        db.add(risk)
        risks_created.append(risk)

    db.flush()
    logger.info("Created %d risk scores for assessment %s", len(risks_created), assessment_id)
    return risks_created


def generate_recommendations_sync(
    db: Session, assessment_id: uuid.UUID
) -> list[Recommendation]:
    """Generate contract clause recommendations for risks (sync)."""

    risks = db.execute(
        select(RiskAssessment).where(RiskAssessment.assessment_id == assessment_id)
    ).scalars().all()

    if not risks:
        logger.info("No risks found for assessment %s, skipping recommendations", assessment_id)
        return []

    # Gather associated gaps
    gap_ids = [r.gap_id for r in risks]
    gaps = db.execute(
        select(GapAssessment).where(GapAssessment.id.in_(gap_ids))
    ).scalars().all()
    gap_map = {str(g.id): g for g in gaps}

    risks_data = json.dumps([
        {
            "risk_id": str(r.id),
            "gap_id": str(r.gap_id),
            "risk_level": r.risk_level,
            "rationale": r.rationale,
            "gap_description": gap_map[str(r.gap_id)].description if str(r.gap_id) in gap_map else "",
            "gap_type": gap_map[str(r.gap_id)].gap_type if str(r.gap_id) in gap_map else "",
        }
        for r in risks
    ], indent=2)

    # Search for existing relevant contract clauses
    clause_results = search_contract_clauses_sync(
        db, "vendor security data protection obligations", top_k=10
    )
    existing_clauses = json.dumps(clause_results, indent=2)

    user_prompt = render_prompt("recommendation", {
        "risks_data": risks_data,
        "existing_clauses": existing_clauses,
    })
    system_prompt = get_system_prompt("recommendation")

    result = call_llm_json(user_prompt, system_prompt=system_prompt)

    # Store recommendations
    risk_id_map = {str(r.id): r.id for r in risks}
    recs_created = []

    for rec_data in result.get("recommendations", []):
        # Map gap_id back to the corresponding risk_assessment
        gap_id_str = rec_data.get("gap_id", "")
        risk_id = None
        for r in risks:
            if str(r.gap_id) == gap_id_str:
                risk_id = r.id
                break
        if not risk_id:
            continue

        rec = Recommendation(
            risk_assessment_id=risk_id,
            clause_text=rec_data.get("recommended_clause", ""),
            justification=rec_data.get("justification", ""),
        )
        db.add(rec)
        recs_created.append(rec)

    db.flush()
    logger.info("Created %d recommendations for assessment %s", len(recs_created), assessment_id)
    return recs_created
