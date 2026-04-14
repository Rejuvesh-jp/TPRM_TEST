import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import (
    Assessment, Question, Questionnaire, Artifact, ArtifactChunk, ArtifactInsight,
    GapAssessment, Policy, ContractClause,
)
from app.services.retrieval_service import (
    search_artifact_chunks_sync, search_policies_sync, search_contract_clauses_sync,
)
from app.utils.llm import call_llm_json
from app.utils.prompts import render_prompt, get_system_prompt

logger = logging.getLogger("tprm.gap_analysis_service")


def run_gap_analysis_sync(db: Session, assessment_id: uuid.UUID) -> list[GapAssessment]:
    """Run gap analysis for an assessment (sync)."""

    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise ValueError(f"Assessment {assessment_id} not found")

    # Gather questionnaire insights
    questionnaires = db.execute(
        select(Questionnaire).where(Questionnaire.assessment_id == assessment_id)
    ).scalars().all()

    questions = []
    for q in questionnaires:
        q_questions = db.execute(
            select(Question).where(Question.questionnaire_id == q.id)
        ).scalars().all()
        questions.extend(q_questions)

    questionnaire_insights = json.dumps([
        {
            "control_id": q.control_id,
            "section": q.section,
            "question": q.question_text,
            "response": q.response_text,
            "justification": q.justification,
            "risk_relevance": q.risk_relevance,
            "claim_strength": q.claim_strength,
            "flags": q.flags,
        }
        for q in questions
    ], indent=2)

    # Gather artifact evidence via retrieval
    artifact_evidence_items = []
    for q in questions:
        if q.risk_relevance in ("high", "critical"):
            query = f"{q.section}: {q.question_text}"
            results = search_artifact_chunks_sync(
                db, query, str(assessment_id), top_k=3
            )
            artifact_evidence_items.extend(results)

    # Deduplicate by chunk ID
    seen_ids = set()
    unique_evidence = []
    for item in artifact_evidence_items:
        if item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            unique_evidence.append(item)

    artifact_evidence = json.dumps(unique_evidence[:30], indent=2)

    # Gather policy context
    policy_results = search_policies_sync(db, "security compliance controls", top_k=5)
    policy_context = json.dumps(policy_results, indent=2)

    # Gather contract clause context
    contract_results = search_contract_clauses_sync(
        db, "vendor obligations security data protection", top_k=5
    )
    contract_context = json.dumps(contract_results, indent=2)

    # Call LLM for gap analysis
    user_prompt = render_prompt("gap_analysis", {
        "questionnaire_insights": questionnaire_insights,
        "artifact_evidence": artifact_evidence,
        "policy_context": policy_context,
        "contract_context": contract_context,
    })
    system_prompt = get_system_prompt("gap_analysis")

    result = call_llm_json(user_prompt, system_prompt=system_prompt)

    # Store gaps
    gaps_created = []
    question_map = {q.control_id: q.id for q in questions if q.control_id}

    for gap_data in result.get("gaps", []):
        related_question_id = None
        related_q_id_str = gap_data.get("related_question_id")
        if related_q_id_str and related_q_id_str in question_map:
            related_question_id = question_map[related_q_id_str]

        gap = GapAssessment(
            assessment_id=assessment_id,
            question_id=related_question_id,
            gap_type=gap_data.get("gap_type", "unknown"),
            description=gap_data.get("description", ""),
            severity=gap_data.get("severity", "medium"),
            source_refs=gap_data.get("source_refs"),
        )
        db.add(gap)
        gaps_created.append(gap)

    db.flush()
    logger.info("Created %d gaps for assessment %s", len(gaps_created), assessment_id)
    return gaps_created
