"""
Azure AD SSO Routes
===================
OAuth 2.0 + OpenID Connect Authorization Code Flow via MSAL.

Routes:
    GET /auth/login    — redirect user to Microsoft login
    GET /auth/callback — exchange auth code for token, create app session
    GET /auth/logout   — destroy app session and redirect to /login
"""
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from webapp.config import (
    SSO_REDIRECT_URI,
    SSO_SCOPES,
    SSO_ENABLED,
)

def _get_redirect_uri(request: Request) -> str:
    """Build redirect URI dynamically from the incoming request.
    Uses REDIRECT_URI from .env if set, otherwise constructs from request base URL.
    This allows the same codebase to work on both localhost and production server."""
    if SSO_REDIRECT_URI:
        return SSO_REDIRECT_URI
    # Auto-detect from request
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost:8085"))
    return f"{scheme}://{host}/auth/callback"
from webapp.auth import create_session, destroy_session, _log_login_activity
from webapp.obo_token import get_shared_msal_app, store_user_token

logger = logging.getLogger("tprm.sso")

router = APIRouter(prefix="/auth", tags=["sso"])


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #

@router.get("/login")
async def sso_login(request: Request):
    """Redirect user to Microsoft Azure AD login page."""
    if not SSO_ENABLED:
        return RedirectResponse("/login?error=sso_disabled")

    state = secrets.token_urlsafe(32)
    auth_url = get_shared_msal_app().get_authorization_request_url(
        SSO_SCOPES,
        state=state,
        redirect_uri=_get_redirect_uri(request),
    )
    response = RedirectResponse(auth_url, status_code=302)
    # Store state in a short-lived HttpOnly cookie to validate on callback (CSRF guard)
    response.set_cookie(
        "sso_state", state,
        httponly=True, samesite="lax",
        max_age=600,
        secure=request.url.scheme == "https",
    )
    return response


@router.get("/callback")
async def sso_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
):
    """Handle Azure AD redirect after authentication."""
    # ── Error returned by Azure ──────────────────────────────────────────────
    if error:
        logger.warning("SSO error from Azure: %s — %s", error, error_description)
        return RedirectResponse("/login?error=sso_failed")

    if not code:
        return RedirectResponse("/login?error=sso_no_code")

    # ── Validate OAuth state (prevents CSRF on the auth flow) ───────────────
    expected_state = request.cookies.get("sso_state", "")
    if not state or not expected_state or not hmac.compare_digest(state, expected_state):
        logger.warning("SSO callback: state mismatch — possible CSRF attempt")
        return RedirectResponse("/login?error=sso_state_mismatch")

    # ── Exchange auth code for token (shared instance populates token cache) ────
    result = get_shared_msal_app().acquire_token_by_authorization_code(
        code,
        scopes=SSO_SCOPES,
        redirect_uri=_get_redirect_uri(request),
    )
    if "error" in result:
        logger.warning(
            "MSAL token acquisition failed: %s — %s",
            result.get("error"), result.get("error_description"),
        )
        return RedirectResponse("/login?error=token_failed")

    # ── Extract identity claims from ID token ────────────────────────────────
    claims = result.get("id_token_claims", {})
    email = (
        claims.get("upn")
        or claims.get("preferred_username")
        or claims.get("email", "")
    ).lower().strip()
    name = claims.get("name", email.split("@")[0] if "@" in email else email)

    if not email:
        logger.warning("SSO callback: no email found in token claims")
        return RedirectResponse("/login?error=sso_no_email")

    # ── Create app session (identical to form login) ─────────────────────────
    role = _get_or_create_user(email, name)
    token = create_session({"email": email, "name": name, "role": role})

    # ── Store user access token for OBO gateway calls ───────────────────────────
    # result["access_token"] is the gateway-scoped token (access_as_user)
    # OBO module exchanges this for a gateway OBO token on each AI call
    user_access_token = result.get("access_token")
    if user_access_token:
        store_user_token(email, user_access_token)
    else:
        logger.warning("SSO callback: no access_token in result for %s", email)

    # ── Log login activity (same as form login) ──────────────────────────────
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "Unknown")
    _log_login_activity(email, name, True, ip_address, user_agent)

    response = RedirectResponse(url="/home", status_code=302)
    response.set_cookie(
        "session_token", token,
        httponly=True, samesite="lax",
        secure=request.url.scheme == "https",
    )
    response.delete_cookie("sso_state")
    logger.info("SSO login successful: %s (%s)", email, role)
    return response


@router.get("/logout")
async def sso_logout(request: Request):
    """Destroy session and redirect to login page."""
    destroy_session(request)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    return response


# --------------------------------------------------------------------------- #
# Helper                                                                       #
# --------------------------------------------------------------------------- #

def _get_or_create_user(email: str, name: str) -> str:
    """Return the user's role.  Auto-provisions as 'analyst' on first SSO login."""
    from webapp.models import AppUser
    from webapp.db import SessionLocal

    with SessionLocal() as session:
        row = session.query(AppUser).filter(AppUser.email.ilike(email)).first()
        if row:
            return row.role

        # First-time SSO login: create user with sentinel password_hash
        now = datetime.now(timezone.utc).isoformat()
        session.add(AppUser(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
            role="analyst",
            password_hash="__sso__",   # cannot be used for form login
            is_active=True,
            created_at=now,
            updated_at=now,
        ))
        session.commit()
        logger.info("Auto-provisioned new SSO user: %s (analyst)", email)
        return "analyst"
