"""
Database Storage Manager
========================
PostgreSQL-backed storage for assessments, replacing JSON file storage.
Drop-in replacement for the old file-based webapp/storage.py.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, delete

from webapp.db import get_session
from webapp.models import Assessment, AssessmentFile, PipelineOutput, DefaultDocument

logger = logging.getLogger("tprm.storage")


def _strip_null_bytes(obj):
    """Recursively strip NULL bytes from strings in a data structure.

    PostgreSQL text/JSONB columns cannot store \\x00 characters.
    """
    if isinstance(obj, str):
        return obj.replace("\x00", "")
    if isinstance(obj, dict):
        return {_strip_null_bytes(k): _strip_null_bytes(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_null_bytes(item) for item in obj]
    return obj

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

INPUT_SUBDIRS = ["questionnaires", "pre_business_assessment", "artifacts", "policies", "contract_clauses"]


def lookup_vendor_by_id(vendor_id: str) -> dict | None:
    """Return the latest vendor_name and next version for a given vendor_id."""
    with get_session() as session:
        rows = session.execute(
            select(Assessment.vendor_name, Assessment.version, Assessment.division)
            .where(Assessment.vendor_id == vendor_id)
            .order_by(Assessment.version.desc())
            .limit(1)
        ).first()
        if not rows:
            return None
        return {
            "vendor_id": vendor_id,
            "vendor_name": rows.vendor_name,
            "latest_version": rows.version,
            "next_version": rows.version + 1,
            "division": rows.division or "",
        }


def create_assessment(vendor_name: str, use_openai: bool = False, division: str = "", nature_of_engagement: str = "", spoc_email: str = "", pre_assessment_scores: dict | None = None, created_by_email: str | None = None) -> dict:
    """Create a new assessment and return metadata dict.

    Vendor ID is deterministic (MD5 of normalised name) so the same vendor
    always gets the same VND-XXXXXX identifier across versions.
    Version is max(existing version for this vendor) + 1.
    """
    aid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Deterministic vendor ID: first 6 hex chars of MD5 of lower-trimmed name
    vendor_norm = vendor_name.strip().lower()
    # MD5 used only as a deterministic short identifier, NOT for security.
    vendor_id = "VND-" + hashlib.md5(vendor_norm.encode(), usedforsecurity=False).hexdigest()[:6].upper()

    with get_session() as session:
        # Next version = max existing version for this vendor + 1
        result = session.execute(
            select(Assessment.version)
            .where(Assessment.vendor_id == vendor_id)
            .order_by(Assessment.version.desc())
            .limit(1)
        ).scalar()
        version = (result or 0) + 1

        assessment = Assessment(
            id=aid,
            vendor_name=vendor_name,
            vendor_id=vendor_id,
            version=version,
            division=division.strip() if division else None,
            nature_of_engagement=nature_of_engagement.strip().lower() if nature_of_engagement else None,
            pre_assessment_scores=pre_assessment_scores,
            spoc_email=spoc_email.strip().lower() if spoc_email else None,
            created_by_email=created_by_email.strip().lower() if created_by_email else None,
            status=STATUS_PENDING,
            use_openai=use_openai,
            created_at=now,
            progress={"current_step": 0, "total_steps": 7, "step_label": ""},
        )
        session.add(assessment)
        session.commit()
        meta = assessment.to_meta()

    logger.info("Created assessment %s for vendor '%s' (vendor_id=%s, v%d, division=%s, engagement=%s)", aid, vendor_name, vendor_id, version, division or '—', nature_of_engagement or '—')
    return meta


def set_risk_rating(assessment_id: str, risk_rating: str) -> bool:
    """Manually assign the vendor risk rating (high / medium / low) for an assessment."""
    with get_session() as session:
        row = session.execute(
            select(Assessment).where(Assessment.id == assessment_id)
        ).scalar_one_or_none()
        if not row:
            return False
        row.risk_rating = risk_rating
        session.commit()
    return True


def save_uploaded_file(assessment_id: str, category: str, filename: str, content: bytes):
    """Save an uploaded file into the database."""
    if category not in INPUT_SUBDIRS:
        raise ValueError(f"Invalid category: {category}")

    af = AssessmentFile(
        assessment_id=assessment_id,
        category=category,
        filename=filename,
        file_data=content,
    )

    with get_session() as session:
        session.add(af)
        session.commit()

    logger.info("Saved upload: %s/%s/%s", assessment_id[:8], category, filename)


def get_assessment(assessment_id: str) -> dict | None:
    """Get assessment metadata."""
    with get_session() as session:
        a = session.get(Assessment, assessment_id)
        if not a:
            return None
        return a.to_meta()


def update_status(assessment_id: str, status: str, **kwargs):
    """Update assessment status and optional fields."""
    with get_session() as session:
        a = session.get(Assessment, assessment_id)
        if not a:
            return
        a.status = status
        for k, v in kwargs.items():
            if hasattr(a, k):
                setattr(a, k, v)
        session.commit()


def update_progress(assessment_id: str, step: int, label: str):
    """Update pipeline progress."""
    with get_session() as session:
        a = session.get(Assessment, assessment_id)
        if not a:
            return
        a.progress = {"current_step": step, "total_steps": 7, "step_label": label}
        session.commit()


def list_assessments(owner_email: str | None = None) -> list[dict]:
    """List assessments sorted by creation date (newest first).

    If *owner_email* is provided only assessments created by that user are
    returned (used to enforce IDOR restriction for non-admin roles).
    """
    with get_session() as session:
        stmt = (
            select(Assessment)
            .where(Assessment.status != "deleted")
        )
        if owner_email is not None:
            stmt = stmt.where(Assessment.created_by_email == owner_email.strip().lower())
        stmt = stmt.order_by(Assessment.created_at.desc())
        results = session.scalars(stmt).all()
        return [a.to_meta() for a in results]


def delete_assessment(assessment_id: str) -> bool:
    """Delete an assessment and renumber remaining versions for the same vendor."""
    with get_session() as session:
        a = session.get(Assessment, assessment_id)
        if not a:
            return False
        vendor_id = a.vendor_id
        session.delete(a)
        session.flush()  # apply delete before renumbering

        # Renumber remaining versions for this vendor: v1, v2, v3, ...
        if vendor_id:
            remaining = session.scalars(
                select(Assessment)
                .where(Assessment.vendor_id == vendor_id)
                .order_by(Assessment.version.asc())
            ).all()
            for idx, row in enumerate(remaining, start=1):
                row.version = idx

        session.commit()
    logger.info("Deleted assessment %s (versions renumbered for vendor %s)", assessment_id, vendor_id)
    return True


def get_assessment_dir(assessment_id: str):
    """Compatibility shim — not used with DB storage."""
    return None


def get_output_file(assessment_id: str, filename: str):
    """Compatibility shim — not used with DB storage."""
    return None


def get_report_data(assessment_id: str) -> dict | None:
    """Load the full assessment report from DB."""
    with get_session() as session:
        a = session.get(Assessment, assessment_id)
        if not a:
            return None
        return a.report_data


def save_report_data(assessment_id: str, report: dict):
    """Save the full assessment report to DB."""
    with get_session() as session:
        a = session.get(Assessment, assessment_id)
        if not a:
            return
        a.report_data = report
        
        # Update assessment metadata summary to match report summary
        # This ensures dashboard and analytics show correct counts
        if "summary" in report:
            a.summary = report["summary"]
        
        session.commit()


def get_input_file_counts(assessment_id: str) -> dict:
    """Count files in each input category."""
    counts = {sub: 0 for sub in INPUT_SUBDIRS}
    with get_session() as session:
        stmt = (
            select(AssessmentFile.category)
            .where(AssessmentFile.assessment_id == assessment_id)
        )
        rows = session.execute(stmt).all()
        for (cat,) in rows:
            if cat in counts:
                counts[cat] += 1
    return counts


def get_uploaded_files(assessment_id: str, category: str) -> list[tuple[str, bytes]]:
    """Get all uploaded files for an assessment category.
    Returns list of (filename, file_data) tuples."""
    with get_session() as session:
        stmt = (
            select(AssessmentFile)
            .where(
                AssessmentFile.assessment_id == assessment_id,
                AssessmentFile.category == category,
            )
        )
        files = session.scalars(stmt).all()
        return [(f.filename, f.file_data) for f in files]


def save_pipeline_output(assessment_id: str, step_name: str, data: dict):
    """Save a pipeline step output to DB."""
    data = _strip_null_bytes(data)
    with get_session() as session:
        existing = session.execute(
            select(PipelineOutput).where(
                PipelineOutput.assessment_id == assessment_id,
                PipelineOutput.step_name == step_name,
            )
        ).scalar_one_or_none()
        if existing:
            existing.output_data = data
        else:
            session.add(PipelineOutput(
                assessment_id=assessment_id,
                step_name=step_name,
                output_data=data,
            ))
        session.commit()


def get_pipeline_output(assessment_id: str, step_name: str) -> dict | None:
    """Load a pipeline step output from DB."""
    with get_session() as session:
        result = session.execute(
            select(PipelineOutput).where(
                PipelineOutput.assessment_id == assessment_id,
                PipelineOutput.step_name == step_name,
            )
        ).scalar_one_or_none()
        return result.output_data if result else None


def get_previous_gaps_for_vendor(vendor_id: str, exclude_assessment_id: str) -> list[dict] | None:
    """Load gap analysis results from the most recent COMPLETED assessment
    for the same vendor, excluding the current assessment.

    Returns the list of gap dicts, or None if no prior assessment exists.
    """
    with get_session() as session:
        # Find the most recent completed assessment for this vendor (by version desc)
        prev_assessment = session.execute(
            select(Assessment.id)
            .where(
                Assessment.vendor_id == vendor_id,
                Assessment.id != exclude_assessment_id,
                Assessment.status == "completed",
            )
            .order_by(Assessment.version.desc())
        ).scalars().first()

        if not prev_assessment:
            return None

        # Load its gap analysis output
        gap_output = session.execute(
            select(PipelineOutput.output_data)
            .where(
                PipelineOutput.assessment_id == prev_assessment,
                PipelineOutput.step_name == "5_gap_analysis",
            )
        ).scalars().first()

        if not gap_output:
            return None

        return gap_output.get("gaps", [])


# --------------- Default Documents (preloaded policies / clauses) ---------------

def _next_version(session, category: str) -> int:
    """Get the next version number for a category."""
    from sqlalchemy import func
    max_ver = session.execute(
        select(func.max(DefaultDocument.version)).where(DefaultDocument.category == category)
    ).scalar()
    return (max_ver or 0) + 1


def save_default_document(category: str, filename: str, file_data: bytes, version: int | None = None) -> str:
    """Save a default document with auto-versioning. Returns its ID.
    If version is None, auto-increments. New uploads are set as active
    (deactivating previous versions in that category)."""
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_session() as session:
        if version is None:
            version = _next_version(session, category)
        label = f"v{version}"
        # Deactivate all previous versions in this category
        session.execute(
            DefaultDocument.__table__.update()
            .where(DefaultDocument.category == category)
            .values(is_active=False)
        )
        session.add(DefaultDocument(
            id=doc_id,
            category=category,
            filename=filename,
            version=version,
            version_label=label,
            is_active=True,
            file_data=file_data,
            uploaded_at=now,
        ))
        session.commit()
    logger.info("Saved default document '%s' %s (%s)", filename, label, category)
    return doc_id


def get_default_documents(category: str) -> list[dict]:
    """Return list of all default documents for a category (without file_data), all versions."""
    with get_session() as session:
        rows = session.execute(
            select(DefaultDocument)
            .where(DefaultDocument.category == category)
            .order_by(DefaultDocument.version.desc())
        ).scalars().all()
        return [
            {
                "id": r.id,
                "category": r.category,
                "filename": r.filename,
                "version": r.version,
                "version_label": r.version_label,
                "is_active": r.is_active,
                "uploaded_at": r.uploaded_at,
                "has_processed_data": r.processed_data is not None,
            }
            for r in rows
        ]


def get_active_default_documents(category: str) -> list[dict]:
    """Return only the active version documents for a category (without file_data)."""
    with get_session() as session:
        rows = session.execute(
            select(DefaultDocument).where(
                DefaultDocument.category == category,
                DefaultDocument.is_active == True,
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "category": r.category,
                "filename": r.filename,
                "version": r.version,
                "version_label": r.version_label,
                "is_active": r.is_active,
                "uploaded_at": r.uploaded_at,
                "has_processed_data": r.processed_data is not None,
            }
            for r in rows
        ]


def get_default_document_files(category: str) -> list[tuple[str, bytes]]:
    """Return (filename, file_data) tuples for the active version in a category."""
    with get_session() as session:
        rows = session.execute(
            select(DefaultDocument).where(
                DefaultDocument.category == category,
                DefaultDocument.is_active == True,
            )
        ).scalars().all()
        return [(r.filename, r.file_data) for r in rows]


def get_default_processed_data(category: str) -> list[dict] | None:
    """Return the pre-computed processed data for active default docs in a category.
    Returns None if no active docs exist or any hasn't been processed yet."""
    with get_session() as session:
        rows = session.execute(
            select(DefaultDocument).where(
                DefaultDocument.category == category,
                DefaultDocument.is_active == True,
            )
        ).scalars().all()
        if not rows:
            return None
        results = []
        for r in rows:
            if r.processed_data is None:
                return None  # not all processed
            results.extend(r.processed_data if isinstance(r.processed_data, list) else [r.processed_data])
        return results


def save_default_processed_data(doc_id: str, processed_data):
    """Save pre-computed processed data (with embeddings) for a default document."""
    with get_session() as session:
        doc = session.get(DefaultDocument, doc_id)
        if doc:
            doc.processed_data = processed_data
            session.commit()


def set_active_version(category: str, version: int) -> bool:
    """Set a specific version as active for a category, deactivating all others."""
    with get_session() as session:
        # Deactivate all
        session.execute(
            DefaultDocument.__table__.update()
            .where(DefaultDocument.category == category)
            .values(is_active=False)
        )
        # Activate the selected version
        result = session.execute(
            DefaultDocument.__table__.update()
            .where(
                DefaultDocument.category == category,
                DefaultDocument.version == version,
            )
            .values(is_active=True)
        )
        session.commit()
        return result.rowcount > 0


def get_version_list(category: str) -> list[dict]:
    """Get a summary of all versions for a category (for the version picker)."""
    from sqlalchemy import func
    with get_session() as session:
        rows = session.execute(
            select(
                DefaultDocument.version,
                DefaultDocument.version_label,
                DefaultDocument.is_active,
                DefaultDocument.uploaded_at,
                func.count(DefaultDocument.id).label("file_count"),
                func.bool_and(DefaultDocument.processed_data.isnot(None)).label("all_processed"),
            )
            .where(DefaultDocument.category == category)
            .group_by(
                DefaultDocument.version,
                DefaultDocument.version_label,
                DefaultDocument.is_active,
                DefaultDocument.uploaded_at,
            )
            .order_by(DefaultDocument.version.desc())
        ).all()
        return [
            {
                "version": r.version,
                "version_label": r.version_label,
                "is_active": r.is_active,
                "uploaded_at": r.uploaded_at,
                "file_count": r.file_count,
                "all_processed": r.all_processed,
            }
            for r in rows
        ]


def delete_default_document(doc_id: str) -> bool:
    """Delete a default document by ID."""
    with get_session() as session:
        result = session.execute(
            delete(DefaultDocument).where(DefaultDocument.id == doc_id)
        )
        session.commit()
        return result.rowcount > 0


def delete_default_version(category: str, version: int) -> int:
    """Delete all documents in a specific version. Returns count deleted."""
    with get_session() as session:
        result = session.execute(
            delete(DefaultDocument).where(
                DefaultDocument.category == category,
                DefaultDocument.version == version,
            )
        )
        session.commit()
        return result.rowcount


def delete_all_default_documents(category: str) -> int:
    """Delete all default documents in a category. Returns count deleted."""
    with get_session() as session:
        result = session.execute(
            delete(DefaultDocument).where(DefaultDocument.category == category)
        )
        session.commit()
        return result.rowcount
