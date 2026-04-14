"""
REST API Routes
===============
JSON API endpoints for assessment CRUD and pipeline execution.
"""
import html
import json
import logging
from pathlib import Path

import magic
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from webapp import db_storage as storage
from webapp.limiter import limiter
from webapp.pipeline_runner import run_pipeline_async
from webapp.auth import require_auth, validate_credentials, create_session, is_account_locked, LOCKOUT_MINUTES

logger = logging.getLogger("tprm.api")
router = APIRouter(prefix="/api")

class LoginRequest(BaseModel):
    username: str
    password: str


def _check_auth(request: Request) -> dict:
    """Authenticate and return the current user dict. Raises 401 if not authenticated."""
    user = require_auth(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def _check_assessment_access(request: Request, assessment_id: str) -> tuple[dict, dict]:
    """Authenticate, load assessment, and enforce ownership.

    Returns (user, assessment_meta).
    Admins can access any assessment.
    Non-admin users can only access assessments they created.
    """
    user = _check_auth(request)
    meta = storage.get_assessment(assessment_id)
    if not meta:
        raise HTTPException(404, "Assessment not found")
    if user.get("role") != "admin":
        owner = (meta.get("created_by_email") or "").lower()
        if owner and owner != user["email"].lower():
            raise HTTPException(403, "Access denied to this assessment")
    return user, meta

@router.post("/login")
@limiter.limit("5/minute")
async def login(login_request: LoginRequest, request: Request):
    """API login endpoint. Rate-limited to 5 attempts per minute per IP."""
    if is_account_locked(login_request.username):
        raise HTTPException(
            status_code=429,
            detail=f"Account locked due to too many failed attempts. Try again in {LOCKOUT_MINUTES} minutes.",
        )
    user = validate_credentials(login_request.username, login_request.password, request)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_session(user)
    # Set httponly cookie (for browser use) AND return token in body (for API clients).
    # Browser-based code should rely on the cookie; do NOT store the token in JS memory.
    resp = JSONResponse({
        "success": True,
        "message": "Login successful",
        "user": {"email": user["email"], "name": user["name"], "role": user["role"]},
    })
    resp.set_cookie(
        "session_token", token,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return resp

ALLOWED_MIME_TYPES = {
    "application/pdf",                                                                  # .pdf
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",           # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",                 # .xlsx
    "application/vnd.ms-excel",                                                         # .xls
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",         # .pptx
    "application/zip",                                                                  # .zip
    "application/x-zip-compressed",                                                     # .zip (alt)
    "image/png",                                                                        # .png
    "image/jpeg",                                                                       # .jpg/.jpeg
    "text/plain",                                                                       # .txt/.csv/.json
    "text/csv",                                                                         # .csv (alt)
    "application/json",                                                                 # .json (alt)
    "application/csv",                                                                  # .csv (alt)
}
# Text-based formats may all detect as text/plain; allow these extensions when MIME is text
_TEXT_EXTENSIONS = {".txt", ".csv", ".json"}
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".xls", ".pptx", ".json", ".zip", ".png", ".jpg", ".jpeg"}
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB


# Per-category allowed extensions (only categories with restrictions listed)
_CATEGORY_EXTENSIONS = {
    "questionnaires":          {".pdf"},
    "pre_business_assessment": {".pdf", ".docx", ".txt"},
    "policies":                {".pdf", ".docx", ".txt"},
    "contract_clauses":        {".docx", ".pdf", ".txt"},
    # artifacts + defaults: uses the global ALLOWED_EXTENSIONS
}


def _validate_upload(filename: str, content: bytes, category: str | None = None) -> None:
    """Validate file type by reading magic bytes. Raises HTTPException on invalid type."""
    stem = Path(filename).stem
    ext = Path(filename).suffix.lower()

    # Reject double extensions (e.g. "report.exe.pdf", "file.pdf.docx")
    if "." in stem:
        raise HTTPException(
            400,
            f"File '{filename}' contains multiple extensions — not allowed",
        )

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file extension: {ext}")

    # Per-category restriction
    if category and category in _CATEGORY_EXTENSIONS:
        allowed = _CATEGORY_EXTENSIONS[category]
        if ext not in allowed:
            raise HTTPException(
                400,
                f"File '{filename}' — only {', '.join(sorted(allowed))} allowed for {category.replace('_', ' ')}",
            )

    detected_mime = magic.from_buffer(content, mime=True)

    if detected_mime in ("text/plain", "text/x-csv", "text/x-c"):
        # Magic detects many text formats as text/plain — also verify extension
        if ext not in _TEXT_EXTENSIONS:
            raise HTTPException(
                400,
                f"File '{filename}' has text content but unsupported extension '{ext}'",
            )
    elif detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            400,
            f"File '{filename}' has disallowed content type: {detected_mime}",
        )

# ── Pre-Assessment Scoring ───────────────────────────────
PRE_ASSESSMENT_QUESTIONS = [
    {"q": 1, "text": "Is the third party solution a Cloud service (e.g. SaaS, PaaS, IaaS)?", "yes_score": 5},
    {"q": 2, "text": "Does the vendor or its employees have physical / logical access to Titan infrastructure?", "yes_score": 5},
    {"q": 3, "text": "Do the vendor connect to the Titan environment from a non Titan or external network?", "yes_score": 5},
    {"q": 4, "text": "Is the third party developing hardware, software and/or processing data on behalf of Titan?", "yes_score": 5},
    {"q": 5, "text": "Does the vendor have access to Titan's PII (Personally Identifiable Information) data of customers or employee?", "yes_score": 20},
    {"q": 6, "text": "Is the vendor processing any financial data?", "yes_score": 20},
    {"q": 7, "text": "Is Titan's information / systems hosted on supplier premises?", "yes_score": 5},
    {"q": 8, "text": "Has the third party solution or service had an incident (breach) in the past 12 months?", "yes_score": 5},
    {"q": 9, "text": "Does the vendor have access to payment card information?", "yes_score": 20},
    {"q": 10, "text": "Would a failure of this vendor's systems or processes cause Titan to activate its Business Continuity Plan or Disaster Recovery Plan?", "yes_score": 20},
]


def _calculate_pre_assessment(responses: list[dict]) -> dict:
    """Calculate engagement sensitivity from pre-assessment Yes/No responses.

    responses: list of {"q": int, "answer": "yes"|"no"}
    Returns: {"responses": [...], "total_score": N, "sensitivity": "low"|"medium"|"high"}
    """
    answer_map = {r["q"]: r.get("answer", "no").lower() for r in responses}
    breakdown = []
    total = 0
    for qdef in PRE_ASSESSMENT_QUESTIONS:
        ans = answer_map.get(qdef["q"], "no")
        score = qdef["yes_score"] if ans == "yes" else 0
        total += score
        breakdown.append({
            "q": qdef["q"],
            "text": qdef["text"],
            "answer": ans,
            "score": score,
            "max_score": qdef["yes_score"],
        })

    if total <= 10:
        sensitivity = "low"
    elif total <= 20:
        sensitivity = "medium"
    else:
        sensitivity = "high"

    return {"responses": breakdown, "total_score": total, "sensitivity": sensitivity}


@router.get("/vendor-lookup")
async def vendor_lookup(request: Request, vendor_id: str = ""):
    """Return vendor info for a given vendor_id (e.g. VND-093FF9).
    Used by the new-assessment form to auto-fill vendor name."""
    _check_auth(request)
    if not vendor_id or not vendor_id.strip():
        raise HTTPException(400, "vendor_id is required")
    result = storage.lookup_vendor_by_id(vendor_id.strip().upper())
    if not result:
        raise HTTPException(404, f"No vendor found with ID {vendor_id}")
    return JSONResponse(result)


@router.post("/assessments")
async def create_assessment(
    request: Request,
    vendor_name: str = Form(...),
    use_openai: bool = Form(False),
    division: str = Form(default=""),
    nature_of_engagement: str = Form(default=""),
    spoc_email: str = Form(default=""),
    questionnaires: list[UploadFile] = File(default=[]),
    pre_business_assessment: list[UploadFile] = File(default=[]),
    artifacts: list[UploadFile] = File(default=[]),
    policies: list[UploadFile] = File(default=[]),
    contract_clauses: list[UploadFile] = File(default=[]),
):
    """Create a new assessment and upload files."""
    user = _check_auth(request)
    if not vendor_name or not vendor_name.strip():
        raise HTTPException(400, "Vendor name is required")

    # Nature of engagement will be auto-calculated from pre-BA during pipeline
    meta = storage.create_assessment(
        vendor_name.strip(), use_openai, division, nature_of_engagement, spoc_email,
        created_by_email=user["email"],
    )
    aid = meta["id"]

    file_map = {
        "questionnaires": questionnaires,
        "pre_business_assessment": pre_business_assessment,
        "artifacts": artifacts,
        "policies": policies,
        "contract_clauses": contract_clauses,
    }

    total_files = 0
    for category, files in file_map.items():
        for f in files:
            if not f.filename:
                continue
            content = await f.read()
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(400, f"File too large: {f.filename}")
            _validate_upload(f.filename, content, category)
            storage.save_uploaded_file(aid, category, f.filename, content)
            total_files += 1

    logger.info("Assessment %s created with %d files", aid[:8], total_files)
    return JSONResponse({"id": aid, "vendor_name": meta["vendor_name"], "status": meta["status"], "total_files": total_files})


@router.post("/assessments/{assessment_id}/run")
async def run_assessment(request: Request, assessment_id: str):
    """Trigger the pipeline for an assessment."""
    _user, meta = _check_assessment_access(request, assessment_id)
    if meta["status"] == storage.STATUS_RUNNING:
        raise HTTPException(409, "Assessment is already running")

    run_pipeline_async(assessment_id, user_email=_user["email"])
    return JSONResponse({"id": assessment_id, "status": "running"})


@router.get("/assessments/{assessment_id}/status")
async def get_status(request: Request, assessment_id: str):
    """Get assessment status and progress. All authenticated users can poll any assessment."""
    _check_auth(request)
    meta = storage.get_assessment(assessment_id)
    if not meta:
        raise HTTPException(404, "Assessment not found")
    progress = meta.get("progress") or {}
    return JSONResponse({
        "id": meta["id"],
        "status": meta["status"],
        "current_step": progress.get("current_step", 0),
        "total_steps": progress.get("total_steps", 7),
        "step_message": progress.get("step_label", ""),
        "error": meta.get("error"),
        "summary": meta.get("summary"),
    })


@router.get("/assessments/{assessment_id}/results")
async def get_results(request: Request, assessment_id: str):
    """Get full assessment results."""
    _check_auth(request)
    meta = storage.get_assessment(assessment_id)
    if not meta:
        raise HTTPException(404, "Assessment not found")
    if meta["status"] != storage.STATUS_COMPLETED:
        raise HTTPException(400, f"Assessment not completed (status: {meta['status']})")

    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not generated yet")
    return JSONResponse(report)


@router.get("/assessments")
async def list_assessments(request: Request):
    """List assessments. All authenticated users see all assessments."""
    _check_auth(request)
    return JSONResponse(storage.list_assessments(owner_email=None))


@router.delete("/assessments/{assessment_id}")
async def delete_assessment(request: Request, assessment_id: str):
    """Delete an assessment."""
    _user, _meta = _check_assessment_access(request, assessment_id)
    if not storage.delete_assessment(assessment_id):
        raise HTTPException(404, "Assessment not found")
    return JSONResponse({"deleted": True})


# ── Gap & Recommendation Editing ─────────────────────────────

@router.delete("/assessments/{assessment_id}/gaps/{gap_id}")
async def delete_gap(request: Request, assessment_id: str, gap_id: str):
    """Remove a gap and its linked recommendations/remedial actions from the report."""
    _user, _meta = _check_assessment_access(request, assessment_id)
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    original = len(report.get("gaps", []))
    report["gaps"] = [g for g in report.get("gaps", []) if g.get("id") != gap_id]
    if len(report["gaps"]) == original:
        raise HTTPException(404, "Gap not found")
    # Remove recommendations and remedial actions that reference this gap.
    # For recommendations linked to multiple gaps (gap_ids list), only unlink
    # this gap — delete the recommendation only when no linked gaps remain.
    surviving_recs = []
    removed_recs = 0
    for r in report.get("recommendations", []):
        gap_ids = r.get("gap_ids", [r.get("gap_id")])
        if gap_id in gap_ids:
            remaining = [gid for gid in gap_ids if gid != gap_id]
            if remaining:
                r["gap_ids"] = remaining
                r["gap_id"] = remaining[0]
                surviving_recs.append(r)
            else:
                removed_recs += 1
        else:
            surviving_recs.append(r)
    report["recommendations"] = surviving_recs
    removed_rem = len([a for a in report.get("remedial_plan", []) if a.get("gap_id") == gap_id])
    report["remedial_plan"] = [a for a in report.get("remedial_plan", []) if a.get("gap_id") != gap_id]
    _refresh_summary(report)
    storage.save_report_data(assessment_id, report)
    return JSONResponse({
        "deleted": True,
        "remaining": len(report["gaps"]),
        "removed_recommendations": removed_recs,
        "removed_remedial_actions": removed_rem,
    })


@router.post("/assessments/{assessment_id}/gaps")
async def add_gap(request: Request, assessment_id: str):
    """Add a new gap to the report."""
    import uuid as _uuid
    _user, _meta = _check_assessment_access(request, assessment_id)
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    body = await request.json()
    new_gap = {
        "id": str(_uuid.uuid4()),
        "gap_type": body.get("gap_type", "unsupported_claim"),
        "severity": body.get("severity", "medium"),
        "description": body.get("description", "").strip(),
        "related_question_id": body.get("related_question_id", ""),
        "evidence_assessment": body.get("evidence_assessment", "").strip(),
        "comments": body.get("comments", "").strip(),
        "source_refs": {"questionnaire": [], "artifacts": [], "policies": [], "contracts": []},
        "gap_status": "open",
    }
    if not new_gap["description"]:
        raise HTTPException(400, "Description is required")
    report.setdefault("gaps", []).append(new_gap)
    _refresh_summary(report)
    storage.save_report_data(assessment_id, report)
    return JSONResponse(new_gap)


@router.put("/assessments/{assessment_id}/gaps/{gap_id}")
async def update_gap(request: Request, assessment_id: str, gap_id: str):
    """Update an existing gap."""
    _user, _meta = _check_assessment_access(request, assessment_id)
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    body = await request.json()
    for g in report.get("gaps", []):
        if g.get("id") == gap_id:
            for field in ("gap_type", "severity", "description", "related_question_id", "evidence_assessment", "comments"):
                if field in body:
                    g[field] = body[field]
            _refresh_summary(report)
            storage.save_report_data(assessment_id, report)
            return JSONResponse(g)
    raise HTTPException(404, "Gap not found")


@router.patch("/assessments/{assessment_id}/gaps/{gap_id}/status")
async def toggle_gap_status(request: Request, assessment_id: str, gap_id: str):
    """Close a gap (permanently) and delete its linked recommendations/remedial actions."""
    _user, _meta = _check_assessment_access(request, assessment_id)
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    body = await request.json()
    new_status = body.get("gap_status")
    if new_status != "closed":
        raise HTTPException(400, "Only closing gaps is allowed. Use 'closed' status.")
    
    for g in report.get("gaps", []):
        if g.get("id") == gap_id:
            if g.get("gap_status") == "closed":
                raise HTTPException(400, "Gap is already closed")
            
            # Close the gap
            g["gap_status"] = "closed"
            
            # Remove linked recommendations and remedial actions.
            # For recommendations linked to multiple gaps (gap_ids list), only
            # unlink this gap — delete only when no linked gaps remain open.
            surviving_recs = []
            removed_recs = 0
            open_gap_ids = {g2["id"] for g2 in report.get("gaps", [])
                           if g2.get("gap_status") != "closed"}
            for r in report.get("recommendations", []):
                gap_ids = r.get("gap_ids", [r.get("gap_id")])
                if gap_id in gap_ids:
                    remaining = [gid for gid in gap_ids if gid != gap_id and gid in open_gap_ids]
                    if remaining:
                        r["gap_ids"] = remaining
                        r["gap_id"] = remaining[0]
                        surviving_recs.append(r)
                    else:
                        removed_recs += 1
                else:
                    surviving_recs.append(r)
            report["recommendations"] = surviving_recs
            removed_rem = len([a for a in report.get("remedial_plan", []) if a.get("gap_id") == gap_id])
            report["remedial_plan"] = [a for a in report.get("remedial_plan", []) if a.get("gap_id") != gap_id]
            
            _refresh_summary(report)
            storage.save_report_data(assessment_id, report)
            
            return JSONResponse({
                "id": gap_id, 
                "gap_status": "closed",
                "removed_recommendations": removed_recs,
                "removed_remedial_actions": removed_rem
            })
    
    raise HTTPException(404, "Gap not found")


@router.patch("/assessments/{assessment_id}/risk-rating")
async def update_risk_rating(request: Request, assessment_id: str):
    """Manually assign the vendor risk rating for an assessment."""
    _user, _meta = _check_assessment_access(request, assessment_id)
    body = await request.json()
    rating = body.get("risk_rating", "").strip().lower()
    if rating not in ("high", "medium", "low", ""):
        raise HTTPException(400, "risk_rating must be 'high', 'medium', 'low', or empty")
    ok = storage.set_risk_rating(assessment_id, rating or None)
    if not ok:
        raise HTTPException(404, "Assessment not found")
    return JSONResponse({"assessment_id": assessment_id, "risk_rating": rating or None})


@router.delete("/assessments/{assessment_id}/recommendations/{rec_id}")
async def delete_recommendation(request: Request, assessment_id: str, rec_id: str):
    """Remove a recommendation from the report."""
    _user, _meta = _check_assessment_access(request, assessment_id)
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    original = len(report.get("recommendations", []))
    report["recommendations"] = [r for r in report.get("recommendations", []) if r.get("id") != rec_id]
    if len(report["recommendations"]) == original:
        raise HTTPException(404, "Recommendation not found")
    _refresh_summary(report)
    storage.save_report_data(assessment_id, report)
    return JSONResponse({"deleted": True, "remaining": len(report["recommendations"])})


@router.post("/assessments/{assessment_id}/recommendations")
async def add_recommendation(request: Request, assessment_id: str):
    """Add a new recommendation to the report."""
    import uuid as _uuid
    _user, _meta = _check_assessment_access(request, assessment_id)
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    body = await request.json()
    new_rec = {
        "id": str(_uuid.uuid4()),
        "gap_id": body.get("gap_id", ""),
        "clause_text": body.get("clause_text", "").strip(),
        "justification": body.get("justification", "").strip(),
        "source": body.get("source", "new"),
        "source_clause_id": body.get("source_clause_id", ""),
        "priority": body.get("priority", "should_have"),
        "existing_coverage": body.get("existing_coverage", "none"),
    }
    if not new_rec["clause_text"]:
        raise HTTPException(400, "Clause text is required")
    report.setdefault("recommendations", []).append(new_rec)
    _refresh_summary(report)
    storage.save_report_data(assessment_id, report)
    return JSONResponse(new_rec)


@router.put("/assessments/{assessment_id}/recommendations/{rec_id}")
async def update_recommendation(request: Request, assessment_id: str, rec_id: str):
    """Update an existing recommendation."""
    _user, _meta = _check_assessment_access(request, assessment_id)
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    body = await request.json()
    for r in report.get("recommendations", []):
        if r.get("id") == rec_id:
            for field in ("clause_text", "justification", "source", "priority", "existing_coverage", "gap_id"):
                if field in body:
                    r[field] = body[field]
            _refresh_summary(report)
            storage.save_report_data(assessment_id, report)
            return JSONResponse(r)
    raise HTTPException(404, "Recommendation not found")


def _refresh_summary(report: dict):
    """Recalculate gap, remedial plan and recommendation summary counts after edits."""
    from collections import Counter
    gaps = report.get("gaps", [])
    sev_counts = Counter(g.get("severity", "medium") for g in gaps)
    report.setdefault("summary", {})["gap_severity"] = dict(sev_counts)
    report["summary"]["total_gaps"] = len(gaps)
    report["summary"]["total_remedial_actions"] = len(report.get("remedial_plan", []))
    report["summary"]["total_recommendations"] = len(report.get("recommendations", []))


# ── Remedial Plan Editing ──────────────────────────────────────

@router.delete("/assessments/{assessment_id}/remedial/{action_id}")
async def delete_remedial_action(request: Request, assessment_id: str, action_id: str):
    """Remove a remedial action from the report."""
    _user, _meta = _check_assessment_access(request, assessment_id)
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    original = len(report.get("remedial_plan", []))
    report["remedial_plan"] = [a for a in report.get("remedial_plan", []) if a.get("id") != action_id]
    if len(report["remedial_plan"]) == original:
        raise HTTPException(404, "Remedial action not found")
    _refresh_summary(report)
    storage.save_report_data(assessment_id, report)
    return JSONResponse({"deleted": True, "remaining": len(report["remedial_plan"])})


@router.post("/assessments/{assessment_id}/remedial")
async def add_remedial_action(request: Request, assessment_id: str):
    """Add a new remedial action to the report."""
    import uuid as _uuid
    _user, _meta = _check_assessment_access(request, assessment_id)
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    body = await request.json()
    new_action = {
        "id": str(_uuid.uuid4()),
        "gap_id": body.get("gap_id", ""),
        "action": body.get("action", "").strip(),
        "priority": body.get("priority", "medium_term"),
        "timeline": body.get("timeline", "").strip(),
        "owner": body.get("owner", "").strip(),
        "acceptance_criteria": body.get("acceptance_criteria", "").strip(),
    }
    if not new_action["action"]:
        raise HTTPException(400, "Action description is required")
    report.setdefault("remedial_plan", []).append(new_action)
    _refresh_summary(report)
    storage.save_report_data(assessment_id, report)
    return JSONResponse(new_action)


@router.put("/assessments/{assessment_id}/remedial/{action_id}")
async def update_remedial_action(request: Request, assessment_id: str, action_id: str):
    """Update an existing remedial action."""
    _user, _meta = _check_assessment_access(request, assessment_id)
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    body = await request.json()
    for a in report.get("remedial_plan", []):
        if a.get("id") == action_id:
            for field in ("action", "priority", "timeline", "owner", "acceptance_criteria", "gap_id"):
                if field in body:
                    a[field] = body[field]
            _refresh_summary(report)
            storage.save_report_data(assessment_id, report)
            return JSONResponse(a)
    raise HTTPException(404, "Remedial action not found")


# ── Default Documents (preloaded policies / clauses) ──────────

@router.get("/defaults/{category}")
async def list_default_documents(request: Request, category: str):
    """List default documents for a category (policies or contract_clauses)."""
    _check_auth(request)
    if category not in ("policies", "contract_clauses"):
        raise HTTPException(400, "Category must be 'policies' or 'contract_clauses'")
    docs = storage.get_default_documents(category)
    return JSONResponse(docs)


@router.post("/defaults/{category}")
async def upload_default_document(
    request: Request,
    category: str,
    files: list[UploadFile] = File(...),
):
    """Upload one or more default documents for a category."""
    _check_auth(request)
    if category not in ("policies", "contract_clauses"):
        raise HTTPException(400, "Category must be 'policies' or 'contract_clauses'")

    uploaded = []
    for f in files:
        content = await f.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(400, f"File {f.filename} exceeds max upload size")
        _validate_upload(f.filename, content)
        doc_id = storage.save_default_document(category, f.filename, content)
        uploaded.append({"id": doc_id, "filename": f.filename})

    return JSONResponse({"uploaded": uploaded, "count": len(uploaded)})


@router.post("/defaults/{category}/process")
async def process_default_documents(request: Request, category: str):
    """Process (embed) the active version of default documents in a category.
    This runs synchronously and stores the pre-computed data."""
    _check_auth(request)
    if category not in ("policies", "contract_clauses"):
        raise HTTPException(400, "Category must be 'policies' or 'contract_clauses'")

    import os
    import shutil
    import tempfile
    from webapp.db_storage import (
        get_active_default_documents, get_default_document_files,
        save_default_processed_data,
    )

    user = _check_auth(request)
    use_openai = True
    if use_openai:
        from services.embedding_service import openai_embed_text
        import httpx
        from openai import OpenAI
        from webapp.obo_token import get_openai_key
        api_key = get_openai_key(user.get("email"))
        if not api_key:
            raise HTTPException(500, "OPENAI_API_KEY not set")
        embed_fn = openai_embed_text
    else:
        from services.embedding_service import mock_embed_text
        embed_fn = mock_embed_text

    from run_assessment import chunk_text
    from services.policy_processor import process_policies
    from services.clause_processor import process_clauses

    # Write active version files to temp dir for processing
    temp_dir = Path(tempfile.mkdtemp(prefix="tprm_defaults_"))
    try:
        doc_files = storage.get_default_document_files(category)
        if not doc_files:
            raise HTTPException(404, "No active default documents found for this category")
        for filename, file_data in doc_files:
            (temp_dir / filename).write_bytes(file_data)

        if category == "policies":
            results = process_policies(temp_dir, chunk_text, embed_fn)
        else:
            results = process_clauses(temp_dir, embed_fn)

        # Save processed data back to each active document
        docs = storage.get_active_default_documents(category)
        if category == "policies":
            result_map = {r["title"]: r for r in results}
            for doc in docs:
                stem = Path(doc["filename"]).stem
                if stem in result_map:
                    storage.save_default_processed_data(doc["id"], [result_map[stem]])
        else:
            from collections import defaultdict
            clause_map = defaultdict(list)
            for cl in results:
                clause_map[cl["source_file"]].append(cl)
            for doc in docs:
                stem = Path(doc["filename"]).stem
                if stem in clause_map:
                    storage.save_default_processed_data(doc["id"], clause_map[stem])

        return JSONResponse({
            "status": "processed",
            "category": category,
            "total_items": len(results),
        })
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/defaults/{category}/activate/{version}")
async def activate_version(request: Request, category: str, version: int):
    """Set a specific version as the active one for a category."""
    _check_auth(request)
    if category not in ("policies", "contract_clauses"):
        raise HTTPException(400, "Category must be 'policies' or 'contract_clauses'")
    if not storage.set_active_version(category, version):
        raise HTTPException(404, f"Version {version} not found")
    return JSONResponse({"activated": True, "category": category, "version": version})


@router.get("/defaults/{category}/versions")
async def list_versions(request: Request, category: str):
    """List all versions for a category with summary info."""
    _check_auth(request)
    if category not in ("policies", "contract_clauses"):
        raise HTTPException(400, "Category must be 'policies' or 'contract_clauses'")
    versions = storage.get_version_list(category)
    return JSONResponse(versions)


@router.delete("/defaults/{category}")
async def delete_all_defaults(request: Request, category: str, version: int | None = None):
    """Delete default documents in a category. If version is specified, only that version."""
    _check_auth(request)
    if category not in ("policies", "contract_clauses"):
        raise HTTPException(400, "Category must be 'policies' or 'contract_clauses'")
    if version is not None:
        count = storage.delete_default_version(category, version)
    else:
        count = storage.delete_all_default_documents(category)
    return JSONResponse({"deleted": count})


@router.delete("/defaults/doc/{doc_id}")
async def delete_default_document(request: Request, doc_id: str):
    """Delete a single default document."""
    _check_auth(request)
    if not storage.delete_default_document(doc_id):
        raise HTTPException(404, "Document not found")
    return JSONResponse({"deleted": True})


# ── Send Gaps Email via Microsoft Graph API ────────────────────

@router.post("/assessments/{assessment_id}/send-gaps-email")
async def send_gaps_email(request: Request, assessment_id: str):
    """Send selected gaps as an email to the SPOC via Microsoft Graph API (client credentials)."""
    import os
    import httpx as _httpx
    _user, meta = _check_assessment_access(request, assessment_id)

    body = await request.json()
    gap_ids: list = body.get("gap_ids", [])
    subject: str = body.get("subject", f"TPRM Security Gaps \u2013 {meta.get('vendor_name', 'Vendor')}").strip()

    # Recipient: use explicit override from request, fall back to assessment SPOC email
    recipient_override = (body.get("recipient") or "").strip()
    spoc_email = (meta.get("spoc_email") or "").strip()
    to_address = recipient_override or spoc_email
    if not to_address:
        raise HTTPException(400, "No recipient email provided. Please enter a recipient address or set the Titan SPOC Email on the assessment.")

    if not gap_ids:
        raise HTTPException(400, "No gaps selected. Please select at least one gap to send.")

    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Assessment report not found")

    all_gaps = report.get("gaps", [])
    selected_gaps = [g for g in all_gaps if g.get("id") in gap_ids]
    if not selected_gaps:
        raise HTTPException(400, "None of the specified gap IDs were found in this assessment")

    vendor_name = meta.get("vendor_name", "Vendor")
    division = meta.get("division") or ""
    assessment_id_display = meta.get("vendor_id") or assessment_id

    # ── HTML-escape all user-supplied values before embedding in email body ──
    vendor_name_h        = html.escape(vendor_name)
    division_h           = html.escape(division)
    assessment_id_disp_h = html.escape(assessment_id_display)

    # Build HTML email body
    rows_html = ""
    for i, g in enumerate(selected_gaps, 1):
        status       = html.escape(g.get("gap_status") or "open")
        status_color = "#198754" if status == "closed" else "#dc3545"
        status_label = status.capitalize()
        gap_type     = html.escape(g.get("gap_type") or "")
        description  = html.escape(g.get("description") or "")
        evidence     = html.escape(g.get("evidence_assessment") or "")
        rows_html += (
            f'<tr>'
            f'<td style="padding:8px 10px;border:1px solid #dee2e6;text-align:center;color:#6c757d;">{i}</td>'
            f'<td style="padding:8px 10px;border:1px solid #dee2e6;font-family:monospace;font-size:12px;">{gap_type}</td>'
            f'<td style="padding:8px 10px;border:1px solid #dee2e6;">{description}</td>'
            f'<td style="padding:8px 10px;border:1px solid #dee2e6;font-size:12px;color:#6c757d;">{evidence}</td>'
            f'<td style="padding:8px 10px;border:1px solid #dee2e6;text-align:center;">'
            f'<span style="color:{status_color};font-weight:600;">{status_label}</span></td>'
            f'</tr>'
        )

    html_body = f"""
<div style="font-family:Arial,Helvetica,sans-serif;max-width:860px;margin:0 auto;color:#212529;">
  <div style="background:#1a1a2e;padding:20px 28px;border-radius:8px 8px 0 0;">
    <h2 style="margin:0;color:#ffffff;font-size:20px;">Titan TPRM &mdash; Security Gap Notification</h2>
  </div>
  <div style="border:1px solid #dee2e6;border-top:none;padding:24px 28px;border-radius:0 0 8px 8px;">
    <p>Dear Team,</p>
    <p>Please find attached (PFA) the security gap(s) identified for <strong>{vendor_name_h}</strong>
    {(' (' + division_h + ')') if division_h else ''} as part of the Third-Party Risk Management (TPRM) assessment.
    Kindly review the gaps listed below and respond with your action plan or clarifications at the earliest.</p>

    <table style="width:100%;border-collapse:collapse;margin-top:16px;font-size:14px;">
      <thead>
        <tr style="background:#f8f9fa;">
          <th style="padding:10px;border:1px solid #dee2e6;text-align:center;width:36px;">#</th>
          <th style="padding:10px;border:1px solid #dee2e6;">Gap Type</th>
          <th style="padding:10px;border:1px solid #dee2e6;">Description</th>
          <th style="padding:10px;border:1px solid #dee2e6;">Evidence / Document</th>
          <th style="padding:10px;border:1px solid #dee2e6;text-align:center;width:70px;">Status</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>

    <p style="margin-top:24px;">We request you to review the above gaps and revert with your observations or remediation plan. Please feel free to reach out in case of any queries.</p>

    <p style="margin-top:8px;">Total gaps shared: <strong>{len(selected_gaps)}</strong></p>

    <hr style="border:none;border-top:1px solid #dee2e6;margin:24px 0;">
    <p style="margin:0;">Warm Regards,<br>
    <strong>TPRM Team</strong><br>
    <span style="font-size:12px;color:#6c757d;">Titan Company Limited &mdash; Third-Party Risk Management</span><br>
    <span style="font-size:11px;color:#adb5bd;">This is an auto-generated notification. Please do not reply directly to this email.</span>
    </p>
  </div>
</div>
"""

    # Read Graph API credentials
    tenant_id = os.getenv("TENANT_ID", "").strip()
    client_id = os.getenv("CLIENT_ID", "").strip()
    client_secret = os.getenv("CLIENT_SECRET", "").strip()
    sender_email = os.getenv("SENDER_EMAIL", "").strip()

    missing = [k for k, v in [("TENANT_ID", tenant_id), ("CLIENT_ID", client_id),
                                ("CLIENT_SECRET", client_secret), ("SENDER_EMAIL", sender_email)] if not v]
    if missing:
        raise HTTPException(500, f"Mail configuration incomplete. Missing: {', '.join(missing)}")

    # Acquire OAuth token via client credentials grant
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    try:
        async with _httpx.AsyncClient(timeout=30) as hc:
            token_resp = await hc.post(token_url, data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
            })
    except Exception as exc:
        logger.error("Graph token request failed: %s", exc)
        raise HTTPException(502, "Could not reach Microsoft authentication endpoint")

    if token_resp.status_code != 200:
        try:
            terr = token_resp.json()
            terr_msg = terr.get("error_description") or terr.get("error") or token_resp.text[:300]
        except Exception:
            terr_msg = token_resp.text[:300]
        logger.error("Graph token error %s: %s", token_resp.status_code, terr_msg)
        raise HTTPException(502, f"Failed to obtain mail access token from Microsoft: {terr_msg}")

    access_token = token_resp.json().get("access_token", "")
    if not access_token:
        raise HTTPException(502, "Empty access token returned by Microsoft")

    # Send mail via Graph API
    mail_payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_address}}],
        },
        "saveToSentItems": True,
    }
    graph_url = f"https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail"
    try:
        async with _httpx.AsyncClient(timeout=30) as hc:
            mail_resp = await hc.post(
                graph_url,
                json=mail_payload,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            )
    except Exception as exc:
        logger.error("Graph sendMail request failed: %s", exc)
        raise HTTPException(502, "Could not reach Microsoft Graph API")

    if mail_resp.status_code not in (200, 202):
        try:
            gerr = mail_resp.json()
            gerr_code = gerr.get("error", {}).get("code", "")
            gerr_msg  = gerr.get("error", {}).get("message", mail_resp.text[:400])
        except Exception:
            gerr_code = ""
            gerr_msg  = mail_resp.text[:400]
        logger.error("Graph sendMail error %s [%s]: %s", mail_resp.status_code, gerr_code, gerr_msg)
        # Give a helpful hint for the most common 403 cause
        hint = ""
        if mail_resp.status_code == 403:
            hint = (
                " | Likely cause: the Azure AD app registration is missing "
                "'Mail.Send' Application permission with admin consent. "
                "Delegated 'Mail.Send' alone is not enough for app-only (client credentials) flow."
            )
        raise HTTPException(502, f"Microsoft Graph error {mail_resp.status_code} [{gerr_code}]: {gerr_msg}{hint}")

    logger.info("Gaps email sent for assessment %s to %s (%d gaps)", assessment_id, to_address, len(selected_gaps))
    return JSONResponse({"sent": True, "recipient": to_address, "gaps_count": len(selected_gaps)})


# ── Pipeline Settings ──────────────────────────────────────────────────────────

@router.get("/settings/pipeline")
async def get_pipeline_settings(request: Request):
    """Return current pipeline feature-flag settings. Admin only."""
    user = _check_auth(request)
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    from webapp.settings_store import get_settings
    return JSONResponse(get_settings())


@router.post("/settings/pipeline")
async def update_pipeline_settings(request: Request):
    """Update pipeline feature-flag settings. Admin only. Takes effect immediately."""
    user = _check_auth(request)
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    body = await request.json()
    allowed = {"llm_judge_enabled", "llm_cache_enabled"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, f"No recognised settings. Allowed: {sorted(allowed)}")
    from webapp.settings_store import save_settings
    current = save_settings(**updates)
    logger.info("Pipeline settings updated by %s: %s", user.get("email"), updates)
    return JSONResponse({"ok": True, "settings": current})
