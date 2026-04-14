import logging
import uuid

from app.core.database import SyncSessionLocal
from app.models.models import Assessment, Questionnaire
from app.services.questionnaire_service import parse_questionnaire_sync
from app.services.artifact_service import process_artifact_sync
from app.services.gap_analysis_service import run_gap_analysis_sync
from app.services.risk_service import run_risk_assessment_sync, generate_recommendations_sync

logger = logging.getLogger("tprm.tasks")


def parse_questionnaire_task(questionnaire_id: str):
    """Parse and analyze a questionnaire synchronously."""
    logger.info("Starting questionnaire parse for %s", questionnaire_id)
    db = SyncSessionLocal()
    try:
        questionnaire = db.get(Questionnaire, uuid.UUID(questionnaire_id))
        if not questionnaire:
            raise ValueError(f"Questionnaire {questionnaire_id} not found")
        parse_questionnaire_sync(str(questionnaire.id), questionnaire.file_path, db)
        db.commit()
        logger.info("Completed questionnaire parse for %s", questionnaire_id)
    except Exception:
        db.rollback()
        logger.exception("Questionnaire parse failed for %s", questionnaire_id)
        raise
    finally:
        db.close()


def process_artifact_task(artifact_id: str):
    """Process an uploaded artifact synchronously."""
    logger.info("Starting artifact processing for %s", artifact_id)
    db = SyncSessionLocal()
    try:
        process_artifact_sync(str(artifact_id), db)
        db.commit()
        logger.info("Completed artifact processing for %s", artifact_id)
    except Exception:
        db.rollback()
        logger.exception("Artifact processing failed for %s", artifact_id)
        raise
    finally:
        db.close()


def run_gap_analysis_task(assessment_id: str):
    """Run gap analysis for an assessment synchronously."""
    logger.info("Starting gap analysis for assessment %s", assessment_id)
    db = SyncSessionLocal()
    try:
        run_gap_analysis_sync(db, uuid.UUID(assessment_id))
        db.commit()
        logger.info("Completed gap analysis for assessment %s", assessment_id)
    except Exception:
        db.rollback()
        logger.exception("Gap analysis failed for assessment %s", assessment_id)
        raise
    finally:
        db.close()


def run_risk_assessment_task(assessment_id: str):
    """Run risk assessment for an assessment synchronously."""
    logger.info("Starting risk assessment for assessment %s", assessment_id)
    db = SyncSessionLocal()
    try:
        run_risk_assessment_sync(db, uuid.UUID(assessment_id))
        generate_recommendations_sync(db, uuid.UUID(assessment_id))
        db.commit()
        logger.info("Completed risk assessment for assessment %s", assessment_id)
    except Exception:
        db.rollback()
        logger.exception("Risk assessment failed for assessment %s", assessment_id)
        raise
    finally:
        db.close()


def run_full_analysis_task(assessment_id: str):
    """Run the full analysis pipeline: gap → risk → recommendations."""
    logger.info("Starting full analysis pipeline for assessment %s", assessment_id)
    db = SyncSessionLocal()
    try:
        assessment = db.get(Assessment, uuid.UUID(assessment_id))
        if not assessment:
            logger.error("Assessment %s not found", assessment_id)
            return

        assessment.status = "analyzing"
        db.commit()

        # Step 1: Gap analysis
        logger.info("Step 1/3: Gap analysis for %s", assessment_id)
        run_gap_analysis_sync(db, uuid.UUID(assessment_id))
        db.commit()

        # Step 2: Risk assessment
        logger.info("Step 2/3: Risk assessment for %s", assessment_id)
        run_risk_assessment_sync(db, uuid.UUID(assessment_id))
        db.commit()

        # Step 3: Recommendations
        logger.info("Step 3/3: Generating recommendations for %s", assessment_id)
        generate_recommendations_sync(db, uuid.UUID(assessment_id))
        db.commit()

        # Mark complete
        assessment.status = "completed"
        db.commit()
        logger.info("Full analysis pipeline completed for assessment %s", assessment_id)

    except Exception:
        db.rollback()
        try:
            assessment = db.get(Assessment, uuid.UUID(assessment_id))
            if assessment:
                assessment.status = "failed"
                db.commit()
        except Exception:
            db.rollback()
        logger.exception("Full analysis pipeline failed for assessment %s", assessment_id)
        raise
    finally:
        db.close()
