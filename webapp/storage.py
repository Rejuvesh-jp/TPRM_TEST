"""
Assessment Storage Manager
===========================
File-based storage for assessments. Each assessment is a self-contained
directory with inputs, outputs, and vector store sub-folders.

Layout:
    assessments/{uuid}/
        metadata.json
        inputs/questionnaires/
        inputs/artifacts/
        inputs/policies/
        inputs/contract_clauses/
        outputs/
        vector_store/
"""
import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from webapp.config import ASSESSMENTS_DIR

logger = logging.getLogger("tprm.storage")

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

INPUT_SUBDIRS = ["questionnaires", "pre_business_assessment", "artifacts", "policies", "contract_clauses"]


def _meta_path(assessment_id: str) -> Path:
    return ASSESSMENTS_DIR / assessment_id / "metadata.json"


def _read_meta(assessment_id: str) -> dict | None:
    path = _meta_path(assessment_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_meta(assessment_id: str, meta: dict):
    path = _meta_path(assessment_id)
    path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")


def create_assessment(vendor_name: str, use_openai: bool = False) -> dict:
    """Create a new assessment directory structure and return metadata."""
    aid = str(uuid.uuid4())
    base = ASSESSMENTS_DIR / aid

    # Create directory tree
    for sub in INPUT_SUBDIRS:
        (base / "inputs" / sub).mkdir(parents=True, exist_ok=True)
    (base / "outputs").mkdir(parents=True, exist_ok=True)
    (base / "vector_store").mkdir(parents=True, exist_ok=True)

    meta = {
        "id": aid,
        "vendor_name": vendor_name,
        "status": STATUS_PENDING,
        "use_openai": use_openai,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "error": None,
        "progress": {"current_step": 0, "total_steps": 7, "step_label": ""},
        "summary": None,
    }
    _write_meta(aid, meta)
    logger.info("Created assessment %s for vendor '%s'", aid, vendor_name)
    return meta


def save_uploaded_file(assessment_id: str, category: str, filename: str, content: bytes):
    """Save an uploaded file into the assessment's input directory."""
    if category not in INPUT_SUBDIRS:
        raise ValueError(f"Invalid category: {category}")
    dest = ASSESSMENTS_DIR / assessment_id / "inputs" / category / filename
    dest.write_bytes(content)
    logger.info("Saved upload: %s/%s/%s", assessment_id[:8], category, filename)


def get_assessment(assessment_id: str) -> dict | None:
    """Get assessment metadata."""
    return _read_meta(assessment_id)


def update_status(assessment_id: str, status: str, **kwargs):
    """Update assessment status and optional fields."""
    meta = _read_meta(assessment_id)
    if not meta:
        return
    meta["status"] = status
    for k, v in kwargs.items():
        meta[k] = v
    _write_meta(assessment_id, meta)


def update_progress(assessment_id: str, step: int, label: str):
    """Update pipeline progress."""
    meta = _read_meta(assessment_id)
    if not meta:
        return
    meta["progress"] = {"current_step": step, "total_steps": 7, "step_label": label}
    _write_meta(assessment_id, meta)


def list_assessments() -> list[dict]:
    """List all assessments, sorted by creation date (newest first)."""
    results = []
    if not ASSESSMENTS_DIR.exists():
        return results
    for d in ASSESSMENTS_DIR.iterdir():
        if d.is_dir() and (d / "metadata.json").exists():
            meta = _read_meta(d.name)
            if meta and meta.get("status") != "deleted":
                results.append(meta)
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results


def delete_assessment(assessment_id: str) -> bool:
    """Delete an assessment and all its files."""
    path = ASSESSMENTS_DIR / assessment_id
    if not path.exists():
        return False
    try:
        shutil.rmtree(path, ignore_errors=False)
    except OSError:
        # On Windows files may be locked; retry with ignore_errors
        import time
        time.sleep(0.5)
        shutil.rmtree(path, ignore_errors=True)
        # If directory still exists, mark it as deleted via metadata
        if path.exists():
            meta = _read_meta(assessment_id)
            if meta:
                meta["status"] = "deleted"
                _write_meta(assessment_id, meta)
    logger.info("Deleted assessment %s", assessment_id)
    return True


def get_assessment_dir(assessment_id: str) -> Path:
    return ASSESSMENTS_DIR / assessment_id


def get_output_file(assessment_id: str, filename: str) -> Path | None:
    """Get path to an output file if it exists."""
    path = ASSESSMENTS_DIR / assessment_id / "outputs" / filename
    return path if path.exists() else None


def get_report_data(assessment_id: str) -> dict | None:
    """Load the full assessment report JSON."""
    path = get_output_file(assessment_id, "assessment_report.json")
    if not path:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_input_file_counts(assessment_id: str) -> dict:
    """Count files in each input category."""
    base = ASSESSMENTS_DIR / assessment_id / "inputs"
    counts = {}
    for sub in INPUT_SUBDIRS:
        d = base / sub
        if d.exists():
            counts[sub] = len([f for f in d.iterdir() if f.is_file()])
        else:
            counts[sub] = 0
    return counts
