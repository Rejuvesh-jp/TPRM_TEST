"""
TPRM AI — Web Application
===========================
FastAPI app with Jinja2 templates for the TPRM assessment platform.

Usage:
    python -m webapp.main
    # or
    uvicorn webapp.main:app --host 127.0.0.1 --port 8085
"""
import hmac as _hmac
import logging
import os
import sys
import traceback
from pathlib import Path

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

# Fix Windows console encoding
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from webapp.config import APP_NAME, APP_VERSION, HOST, PORT, DEBUG
from webapp.db import init_db, seed_users_from_json, seed_audit_from_json
from webapp.limiter import limiter
from webapp.routes.api import router as api_router
from webapp.routes.pages import router as pages_router
from webapp.routes.user_management import router as user_mgmt_router
from webapp.routes.sso import router as sso_router

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

@asynccontextmanager
async def lifespan(app):
    init_db()
    seed_users_from_json()   # idempotent: import users.json → app_users table
    seed_audit_from_json()   # idempotent: import login_activity.json → login_audit_logs table
    yield


# ── FastAPI App ──────────────────────────────────────────
# Swagger/ReDoc UI only available in DEBUG mode to avoid leaking API schema in production
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
    lifespan=lifespan,
)

# ── Rate limiter ─────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_logger = logging.getLogger("tprm.app")


# ── Global exception handlers — always return JSON for /api/ routes ────
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Return JSON instead of HTML for HTTP errors on API routes."""
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"detail": exc.detail},
            status_code=exc.status_code,
        )
    # For page routes, re-raise so FastAPI renders the default error page
    from starlette.responses import HTMLResponse
    return HTMLResponse(f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>", status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return clean JSON for validation errors."""
    _logger.warning("Validation error on %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        {"detail": "Validation error", "errors": exc.errors()},
        status_code=422,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all: log the traceback and return JSON instead of HTML 500."""
    _logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method, request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        {"detail": "Internal server error"},
        status_code=500,
    )

# ── CORS — restrict to known origins ─────────────────────
# Override via ALLOWED_ORIGINS env var (comma-separated list) for production
_default_origins = f"http://127.0.0.1:{PORT},http://localhost:{PORT}"
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)

# ── Security response headers ─────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]          = "DENY"
    response.headers["X-XSS-Protection"]         = "0"           # rely on CSP, not legacy filter
    response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]        = "geolocation=(), microphone=(), camera=()"
    # Strict-Transport-Security — only meaningful over HTTPS; harmless over HTTP
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Content-Security-Policy — permissive enough not to break Bootstrap served locally
    # and chart.js / Google Fonts used in templates.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' fonts.googleapis.com; "
        "font-src 'self' fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'"
    )
    return response


# ── CSRF protection middleware ────────────────────────────
# Validates X-CSRF-Token header for every state-changing request on authenticated sessions.
# Login endpoints are excluded (unauthenticated — no session token to validate against).
_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_CSRF_SKIP_PATHS   = {"/login", "/api/login"}

@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    if (
        request.method not in _CSRF_SAFE_METHODS
        and request.url.path not in _CSRF_SKIP_PATHS
    ):
        from webapp.auth import get_session as _get_session
        session = _get_session(request)
        if session:   # only validate for authenticated requests
            expected = session.get("csrf_token", "")
            received = request.headers.get("X-CSRF-Token", "")
            if not expected or not received or not _hmac.compare_digest(received, expected):
                return JSONResponse(
                    {"detail": "CSRF token validation failed"},
                    status_code=403,
                )
    return await call_next(request)

# Mount static files
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount routers
app.include_router(api_router)
app.include_router(pages_router)
app.include_router(user_mgmt_router)
app.include_router(sso_router)


@app.get("/health")
async def health():
    """Health check — returns minimal information to avoid version disclosure."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    print(f"\n  TPRM AI Assessment Platform v{APP_VERSION}")
    print(f"  Starting at http://{HOST}:{PORT}")
    print(f"  API docs at http://{HOST}:{PORT}/docs\n")
    uvicorn.run(app, host=HOST, port=PORT)
