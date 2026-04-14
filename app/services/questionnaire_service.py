import json
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.models import Questionnaire, Question, Vendor, Assessment
from app.utils.extraction import extract_text_from_pdf
from app.utils.llm import call_llm_json
from app.utils.prompts import render_prompt, get_system_prompt

logger = logging.getLogger("tprm.questionnaire_service")


async def create_vendor(db: AsyncSession, name: str, domain: str | None = None) -> Vendor:
    vendor = Vendor(name=name, domain=domain)
    db.add(vendor)
    await db.flush()
    return vendor


async def create_assessment(db: AsyncSession, vendor_id: uuid.UUID) -> Assessment:
    assessment = Assessment(vendor_id=vendor_id, status="draft")
    db.add(assessment)
    await db.flush()
    return assessment


async def store_questionnaire(
    db: AsyncSession,
    assessment_id: uuid.UUID,
    file_name: str,
    file_path: str,
    file_size: int,
) -> Questionnaire:
    questionnaire = Questionnaire(
        assessment_id=assessment_id,
        file_name=file_name,
        file_path=file_path,
        file_size=file_size,
        analysis_status="pending",
    )
    db.add(questionnaire)
    await db.flush()
    return questionnaire


def parse_questionnaire_sync(questionnaire_id: str, file_path: str, db: Session):
    """Parse questionnaire PDF and extract structured data (sync)."""
    questionnaire = db.query(Questionnaire).filter(
        Questionnaire.id == uuid.UUID(questionnaire_id)
    ).first()
    if not questionnaire:
        raise ValueError(f"Questionnaire {questionnaire_id} not found")

    questionnaire.analysis_status = "analyzing"
    db.commit()

    try:
        # Extract text from PDF
        text = extract_text_from_pdf(file_path)
        if not text.strip():
            raise ValueError("No text could be extracted from the PDF")

        # Parse with LLM
        prompt = render_prompt("questionnaire_parsing", questionnaire_text=text[:15000])
        system = get_system_prompt("questionnaire_parsing")
        parsed = call_llm_json(prompt=prompt, system_prompt=system)

        questionnaire.parsed_content = parsed

        # Store individual questions
        for section in parsed.get("sections", []):
            for q in section.get("questions", []):
                question = Question(
                    questionnaire_id=questionnaire.id,
                    section=section.get("name", "Unknown"),
                    control_id=q.get("control_id"),
                    question_text=q.get("question_text", ""),
                    response_text=q.get("response_text"),
                    justification=q.get("justification"),
                )
                db.add(question)

        db.commit()
        logger.info(f"Parsed questionnaire {questionnaire_id}: {parsed.get('total_questions', 0)} questions")

        # Run analysis
        _analyze_questionnaire_sync(questionnaire, db)

    except Exception as e:
        questionnaire.analysis_status = "failed"
        db.commit()
        logger.error(f"Failed to parse questionnaire {questionnaire_id}: {e}")
        raise


def _analyze_questionnaire_sync(questionnaire: Questionnaire, db: Session):
    """Run AI analysis on parsed questionnaire data."""
    vendor_name = "Unknown Vendor"
    if questionnaire.parsed_content:
        vendor_name = questionnaire.parsed_content.get("vendor_name", vendor_name) or vendor_name

    prompt = render_prompt(
        "questionnaire_analysis",
        vendor_name=vendor_name,
        questionnaire_data=json.dumps(questionnaire.parsed_content, indent=2)[:15000],
    )
    system = get_system_prompt("questionnaire_analysis")
    analysis = call_llm_json(prompt=prompt, system_prompt=system)

    # Update questions with analysis results
    questions = db.query(Question).filter(
        Question.questionnaire_id == questionnaire.id
    ).all()

    analysis_map = {
        item.get("control_id"): item
        for item in analysis.get("question_analysis", [])
        if item.get("control_id")
    }

    for question in questions:
        if question.control_id and question.control_id in analysis_map:
            qa = analysis_map[question.control_id]
            question.risk_relevance = qa.get("risk_relevance")
            question.claim_strength = qa.get("claim_strength")
            question.expected_evidence = qa.get("expected_evidence")
            question.flags = qa.get("flags")

    questionnaire.analysis_result = analysis
    questionnaire.analysis_status = "completed"
    db.commit()
    logger.info(f"Analyzed questionnaire {questionnaire.id}")
