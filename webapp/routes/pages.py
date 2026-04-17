"""
Page Routes
============
HTML page routes using Jinja2 templates.
"""
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime as _dt
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Form as FastForm
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from webapp import db_storage as storage
from webapp.auth import (
    validate_credentials, create_session, get_session,
    destroy_session, require_auth, login_redirect, get_auth_error,
)
from webapp.config import DEBUG
from webapp.limiter import limiter

logger = logging.getLogger("tprm.pages")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


# ── Auth helpers ─────────────────────────────────────────

def _ctx(request: Request, **extra) -> dict:
    """Build template context with user session."""
    user = get_session(request)
    return {"request": request, "user": user, **extra}


def _require(request: Request):
    """Return user or raise redirect to login."""
    user = require_auth(request)
    if not user:
        return None
    return user


# ── Login / Logout ───────────────────────────────────────

@router.get("/home", response_class=HTMLResponse)
async def home_page(request: Request):
    """Landing page — shown to all users (logged in or not)."""
    user = get_session(request)
    return templates.TemplateResponse("home.html", {"request": request, "user": user})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show login form."""
    if get_session(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/test-api")
async def api_test_page(request: Request):
    """API test page — only accessible in DEBUG mode."""
    if not DEBUG:
        raise HTTPException(404, "Not found")
    user = get_session(request)
    if not user:
        return login_redirect()
    return templates.TemplateResponse("api_test.html", {"request": request})

@router.get("/debug-session")
async def debug_session_page(request: Request):
    """Debug session page — only accessible in DEBUG mode."""
    if not DEBUG:
        raise HTTPException(404, "Not found")
    user = get_session(request)
    if not user:
        return login_redirect()
    return templates.TemplateResponse("debug_session.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def login_submit(request: Request,
                       email: str = FastForm(...),
                       password: str = FastForm(...)):
    """Handle login form submission."""
    user = validate_credentials(email, password, request)
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": get_auth_error(email),
            "email": email,
        })
    token = create_session(user)
    response = RedirectResponse(url="/home", status_code=302)
    # secure=True when served over HTTPS; False for local HTTP dev (won't break)
    response.set_cookie(
        "session_token", token,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@router.get("/logout")
async def logout(request: Request):
    """Log the user out and redirect to login."""
    destroy_session(request)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    return response


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard — overview of all assessments."""
    user = _require(request)
    if not user:
        return login_redirect()
    assessments = storage.list_assessments(owner_email=None)  # all users see all assessments
    total = len(assessments)
    completed = sum(1 for a in assessments if a["status"] == "completed")
    running = sum(1 for a in assessments if a["status"] == "running")
    pending = sum(1 for a in assessments if a["status"] == "pending")
    failed = sum(1 for a in assessments if a["status"] == "failed")
    # Count of distinct vendors that have undergone at least one AI review
    unique_vendors = len({a["vendor_id"] for a in assessments if a.get("vendor_id")})

    # Chart 3: top 8 vendors by gap count (completed only), include assessment month
    chart_vendors = sorted(
        [
            {
                "name": a["vendor_name"],
                "gaps": a["summary"]["total_gaps"],
                "month": _dt.fromisoformat(a["created_at"][:19]).strftime("%b '%y")
                         if a.get("created_at") else "",
            }
            for a in assessments
            if a["status"] == "completed" and a.get("summary")
        ],
        key=lambda x: x["gaps"],
        reverse=True,
    )[:8]

    # Chart 4: assessments created per month for the last 12 months
    months_data: dict = defaultdict(int)
    for a in assessments:
        if a.get("created_at") and len(a["created_at"]) >= 7:
            months_data[a["created_at"][:7]] += 1
    chart_monthly = []
    yr, mo = _dt.now().year, _dt.now().month
    for _ in range(12):
        key = f"{yr}-{mo:02d}"
        chart_monthly.insert(0, {"label": _dt(yr, mo, 1).strftime("%b '%y"), "count": months_data.get(key, 0)})
        mo -= 1
        if mo == 0:
            mo, yr = 12, yr - 1

    # Build distinct division list for filter dropdown
    divisions_list = sorted({a["division"] for a in assessments if a.get("division")})

    return templates.TemplateResponse("dashboard.html", _ctx(request,
        assessments=assessments,
        total=total,
        unique_vendors=unique_vendors,
        completed=completed,
        running=running,
        pending=pending,
        failed=failed,
        chart_vendors=chart_vendors,
        chart_monthly=chart_monthly,
        divisions_list=divisions_list,
    ))


@router.get("/assessments", response_class=HTMLResponse)
async def assessments_list(request: Request):
    """List all assessments."""
    user = _require(request)
    if not user:
        return login_redirect()
    assessments = storage.list_assessments(owner_email=None)  # all users see all assessments
    return templates.TemplateResponse("assessments_list.html", _ctx(request,
        assessments=assessments,
    ))


@router.get("/assessments/new", response_class=HTMLResponse)
async def new_assessment(request: Request):
    """New assessment form."""
    if not _require(request):
        return login_redirect()
    default_policies = storage.get_default_documents("policies")
    default_clauses = storage.get_default_documents("contract_clauses")
    return templates.TemplateResponse("new_assessment.html", _ctx(request,
        default_policies=default_policies,
        default_clauses=default_clauses,
    ))


@router.get("/assessments/{assessment_id}", response_class=HTMLResponse)
async def assessment_detail(request: Request, assessment_id: str):
    """Assessment detail / results page."""
    user = _require(request)
    if not user:
        return login_redirect()
    meta = storage.get_assessment(assessment_id)
    if not meta:
        raise HTTPException(404, "Assessment not found")
    # All authenticated users can view any assessment (read-only)
    # Ownership is enforced only on mutating operations (delete, etc.)

    report = None
    gaps = []
    recommendations = []
    remedial_plan = []
    input_counts = storage.get_input_file_counts(assessment_id)

    questions_map = {}  # control_id -> {question_text, response_text, section}
    if meta["status"] == "completed":
        report = storage.get_report_data(assessment_id)
        if report:
            all_gaps = report.get("gaps", [])
            gaps = all_gaps  # Show all gaps (open and closed)
            remedial_plan = report.get("remedial_plan", [])
            recommendations = report.get("recommendations", [])
        # Load questions from pipeline step 1 output
        q_output = storage.get_pipeline_output(assessment_id, "1_questionnaires")
        if q_output:
            for q_file in q_output.get("questionnaires", []):
                for q in q_file.get("questions", []):
                    cid = q.get("control_id")
                    if cid:
                        questions_map[cid] = {
                            "question_text": q.get("question_text", ""),
                            "response_text": q.get("response_text", ""),
                            "justification": q.get("justification", ""),
                            "section": q.get("section", ""),
                        }

    return templates.TemplateResponse("assessment_detail.html", _ctx(request,
        meta=meta,
        report=report,
        gaps=gaps,
        remedial_plan=remedial_plan,
        recommendations=recommendations,
        input_counts=input_counts,
        questions_map=questions_map,
    ))


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_list(request: Request):
    """Assessment Analytics — pick an assessment to view its dashboard."""
    user = _require(request)
    if not user:
        return login_redirect()
    owner_filter = None  # all users see all assessments
    assessments = [
        a for a in storage.list_assessments(owner_email=owner_filter)
        if a["status"] == "completed"
    ]
    return templates.TemplateResponse("analytics_list.html", _ctx(request,
        assessments=assessments,
    ))


@router.get("/assessments/{assessment_id}/analytics", response_class=HTMLResponse)
async def assessment_analytics(request: Request, assessment_id: str):
    """Per-assessment analytics dashboard."""
    if not _require(request):
        return login_redirect()
    meta = storage.get_assessment(assessment_id)
    if not meta or meta["status"] != "completed":
        raise HTTPException(404, "Completed assessment not found")
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report data not found")

    all_gaps = report.get("gaps", [])
    gaps = all_gaps  # Show all gaps (open and closed)
    open_gaps = [g for g in all_gaps if g.get("gap_status", "open") == "open"]
    recommendations = report.get("recommendations", [])
    remedial = report.get("remedial_plan", [])

    # Gap type breakdown (only open gaps)
    gap_type_counts = dict(Counter(g["gap_type"] for g in open_gaps))

    # Gap open / closed split
    gap_open_count   = len(open_gaps)
    gap_closed_count = len(all_gaps) - len(open_gaps)

    # Recommendation priority split
    rec_priority_counts = dict(Counter(r.get("priority", "unset") for r in recommendations))

    # Remedial action priority split
    remedial_priority_counts = dict(Counter(r.get("priority", "unset") for r in remedial))

    # Recommendation source split (existing / new / future_risk)
    rec_source_counts = dict(Counter(r.get("type", r.get("source", "new")) for r in recommendations))

    # Questions answered vs unanswered
    total_q = report.get("input_summary", {}).get("total_questions", 0)
    unanswered = sum(1 for g in open_gaps if g.get("gap_type") == "control_missing")
    answered = max(0, total_q - unanswered)

    return templates.TemplateResponse("assessment_analytics.html", _ctx(request,
        meta=meta,
        report=report,
        gaps=gaps,
        recommendations=recommendations,
        remedial=remedial,
        gap_type_counts=gap_type_counts,
        gap_open_count=gap_open_count,
        gap_closed_count=gap_closed_count,
        rec_priority_counts=rec_priority_counts,
        remedial_priority_counts=remedial_priority_counts,
        rec_source_counts=rec_source_counts,
        total_questions=total_q,
        answered=answered,
        unanswered=unanswered,
    ))


@router.get("/assessments/{assessment_id}/download/pdf")
async def download_pdf(request: Request, assessment_id: str):
    """Download assessment report as PDF."""
    if not _require(request):
        return login_redirect()
    meta = storage.get_assessment(assessment_id)
    if not meta:
        raise HTTPException(404, "Assessment not found")
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    from webapp.report_generator import generate_pdf
    from datetime import datetime as _dt
    # Inject meta into report for generator (for division, engagement, risk)
    report = dict(report)
    report["meta"] = meta
    buf = generate_pdf(report, meta.get("vendor_name", "Vendor"))
    safe_name = meta.get('vendor_name', 'vendor').replace(' ', '_').replace('/', '_')
    timestamp = _dt.now().strftime("%m-%d-%Y")
    filename = f"{safe_name}_{timestamp}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/assessments/{assessment_id}/download/word")
async def download_word(request: Request, assessment_id: str):
    """Download assessment report as Word document."""
    if not _require(request):
        return login_redirect()
    meta = storage.get_assessment(assessment_id)
    if not meta:
        raise HTTPException(404, "Assessment not found")
    report = storage.get_report_data(assessment_id)
    if not report:
        raise HTTPException(404, "Report not found")
    from webapp.report_generator import generate_word
    from datetime import datetime as _dt
    # Inject meta into report for generator (for division, engagement, risk)
    report = dict(report)
    report["meta"] = meta
    buf = generate_word(report, meta.get("vendor_name", "Vendor"))
    safe_name = meta.get('vendor_name', 'vendor').replace(' ', '_').replace('/', '_')
    timestamp = _dt.now().strftime("%m-%d-%Y")
    filename = f"{safe_name}_{timestamp}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/defaults", response_class=HTMLResponse)
async def admin_defaults(request: Request):
    """Admin page — manage preloaded default policies and contract clauses."""
    if not _require(request):
        return login_redirect()
    from webapp.settings_store import get_settings
    _s = get_settings()
    policies = storage.get_default_documents("policies")
    clauses = storage.get_default_documents("contract_clauses")
    return templates.TemplateResponse("admin_defaults.html", _ctx(request,
        policies=policies,
        clauses=clauses,
        llm_judge_enabled=_s["llm_judge_enabled"],
        llm_cache_enabled=_s["llm_cache_enabled"],
    ))


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page — pipeline feature flags, platform info, cache management."""
    if not _require(request):
        return login_redirect()
    import os as _os
    from webapp.settings_store import get_settings as _gs
    from webapp import config as _cfg
    _s = _gs()
    return templates.TemplateResponse("settings.html", _ctx(request,
        llm_judge_enabled=_s["llm_judge_enabled"],
        llm_cache_enabled=_s["llm_cache_enabled"],
        app_version=_cfg.APP_VERSION,
        llm_model=_os.getenv("OPENAI_MODEL", "gpt-5.4-azure"),
        embedding_model="azure/text-embedding-3-small",
        sso_enabled=_cfg.SSO_ENABLED,
        sso_tenant=_cfg.SSO_TENANT_ID or "—",
        debug_mode=_cfg.DEBUG,
    ))


@router.get("/users", response_class=HTMLResponse)
async def user_management(request: Request):
    """User Management page — manage system users and permissions."""
    user = _require(request)
    if not user:
        return login_redirect()
    
    # Only allow admin users to access user management
    if user.get("role") != "admin":
        raise HTTPException(403, "Access denied. Admin privileges required.")
    
    return templates.TemplateResponse("user_management.html", _ctx(request))
