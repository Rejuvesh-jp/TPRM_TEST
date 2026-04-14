"""
Authentication Module
======================
Session-based authentication with users stored in the database (app_users table).
Admin users can add/update/delete users via the user management API.

Security controls implemented:
- Passwords hashed with bcrypt (CWE-256 mitigated)
- Sessions persisted in app_sessions table -- survive app restarts (no Redis required)
- Session absolute timeout (8 h) and idle timeout (60 min)  (CWE-613 mitigated)
- Account lockout after 5 failed attempts for 15 minutes  (CWE-307 mitigated)
- Login audit log persisted in login_audit_logs table
"""
import logging
import secrets
from datetime import datetime, timezone, timedelta

import bcrypt
from fastapi import Request
from fastapi.responses import RedirectResponse

logger = logging.getLogger("tprm.auth")


# --------------------------------------------------------------------------- #
# DB session factory (lazy import to avoid circular imports at module load)    #
# --------------------------------------------------------------------------- #
def _db():
    from webapp.db import SessionLocal
    return SessionLocal()


# --------------------------------------------------------------------------- #
# Session / lockout constants                                                  #
# --------------------------------------------------------------------------- #
SESSION_ABSOLUTE_HOURS = 8       # absolute maximum lifetime
SESSION_IDLE_MINUTES   = 60      # inactivity timeout

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES     = 15

# In-memory lockout tracker -- intentionally resets on restart.
# {email_lower: {"count": int, "locked_until": datetime | None}}
_failed_logins: dict[str, dict] = {}


# --------------------------------------------------------------------------- #
# Password helpers                                                             #
# --------------------------------------------------------------------------- #

def hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt (work factor 12)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def validate_password_complexity(password: str) -> list[str]:
    """Validate password complexity.  Returns list of violation messages (empty = valid)."""
    import re
    errors = []
    if len(password) < 12:
        errors.append("at least 12 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("at least one lowercase letter")
    if not re.search(r"\d", password):
        errors.append("at least one digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("at least one special character")
    return errors


def _verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored bcrypt hash."""
    if stored.startswith("$2"):
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    import hmac
    logger.warning("Plaintext password detected -- run the password migration!")
    return hmac.compare_digest(password, stored)


# --------------------------------------------------------------------------- #
# Account lockout                                                              #
# --------------------------------------------------------------------------- #

def is_account_locked(email: str) -> bool:
    """Return True if the address is currently locked out."""
    info = _failed_logins.get(email.lower())
    if not info:
        return False
    locked_until = info.get("locked_until")
    if locked_until and datetime.now(timezone.utc) < locked_until:
        return True
    if locked_until:
        _failed_logins.pop(email.lower(), None)
    return False


def _record_failed(email: str) -> None:
    key  = email.lower()
    info = _failed_logins.setdefault(key, {"count": 0, "locked_until": None})
    info["count"] += 1
    if info["count"] >= MAX_FAILED_ATTEMPTS:
        info["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
        logger.warning(
            "Account %s locked for %d min after %d failed attempts",
            email, LOCKOUT_MINUTES, info["count"],
        )


def _reset_failed(email: str) -> None:
    _failed_logins.pop(email.lower(), None)


# --------------------------------------------------------------------------- #
# DB helpers                                                                   #
# --------------------------------------------------------------------------- #

def _load_users() -> list[dict]:
    """Load all active users from app_users table."""
    from webapp.models import AppUser
    with _db() as session:
        rows = session.query(AppUser).filter(AppUser.is_active == True).all()
        return [
            {"email": r.email, "name": r.name, "role": r.role,
             "password_hash": r.password_hash}
            for r in rows
        ]


def _log_login_activity(email: str, name: str, success: bool,
                         ip_address: str = "unknown", user_agent: str = "Unknown"):
    """Persist a login event to the login_audit_logs table."""
    import uuid as _uuid
    from webapp.models import LoginAuditLog
    try:
        now = datetime.now(timezone.utc).isoformat()
        log = LoginAuditLog(
            id=str(_uuid.uuid4()),
            timestamp=now,
            user_email=email,
            name=name,
            action="LOGIN_SUCCESS" if success else "LOGIN_FAILED",
            ip_address=ip_address or "unknown",
            user_agent=(user_agent or "Unknown")[:200],
        )
        with _db() as session:
            session.add(log)
            session.commit()
        logger.info("Login activity logged for %s: %s", email,
                    "SUCCESS" if success else "FAILED")
    except Exception as exc:
        logger.error("Failed to log login activity: %s", exc)


# --------------------------------------------------------------------------- #
# Credential validation                                                        #
# --------------------------------------------------------------------------- #

def validate_credentials(email: str, password: str, request: Request = None) -> dict | None:
    """Validate email + password against app_users table.
    Returns user dict on success, None on failure (wrong credentials or locked out).
    """
    email      = email.strip().lower()
    ip_address = "unknown"
    user_agent = "Unknown"
    if request:
        ip_address = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "Unknown")

    if is_account_locked(email):
        logger.warning("Login blocked -- account locked: %s from %s", email, ip_address)
        _log_login_activity(email, "Locked Account", False, ip_address, user_agent)
        return None

    for user in _load_users():
        if user["email"].lower() == email:
            stored = user.get("password_hash") or user.get("password", "")
            if _verify_password(password, stored):
                _reset_failed(email)
                user_info = {"email": user["email"], "name": user["name"], "role": user["role"]}
                _log_login_activity(email, user["name"], True, ip_address, user_agent)
                return user_info

    _record_failed(email)
    _log_login_activity(email, "Unknown User", False, ip_address, user_agent)
    return None


# --------------------------------------------------------------------------- #
# User CRUD (used by user_management routes)                                   #
# --------------------------------------------------------------------------- #

def add_user(email: str, name: str, password: str, role: str = "analyst") -> bool:
    """Add a new user to the database.  Password is hashed with bcrypt."""
    if not email or not name or not password:
        return False
    import uuid as _uuid
    from webapp.models import AppUser
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _db() as session:
            exists = session.query(AppUser).filter(
                AppUser.email.ilike(email.strip())
            ).first()
            if exists:
                return False
            session.add(AppUser(
                id=str(_uuid.uuid4()),
                email=email.strip(),
                name=name.strip(),
                role=role,
                password_hash=hash_password(password),
                is_active=True,
                created_at=now,
                updated_at=now,
            ))
            session.commit()
        logger.info("User %s added to database", email)
        return True
    except Exception as exc:
        logger.error("add_user failed: %s", exc)
        return False


# --------------------------------------------------------------------------- #
# Session management (DB-backed)                                               #
# --------------------------------------------------------------------------- #

def create_session(user: dict) -> str:
    """Create a new DB-persisted session for an authenticated user.  Returns token."""
    import uuid as _uuid
    from webapp.models import AppSession, AppUser
    token      = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now        = datetime.now(timezone.utc).isoformat()
    try:
        with _db() as session:
            row = session.query(AppUser).filter(
                AppUser.email.ilike(user["email"])
            ).first()
            user_id = row.id if row else str(_uuid.uuid4())
            session.add(AppSession(
                token=token,
                user_id=user_id,
                email=user["email"],
                name=user["name"],
                role=user["role"],
                csrf_token=csrf_token,
                created_at=now,
                last_activity=now,
            ))
            session.commit()
        logger.info("Session created for %s", user["email"])
    except Exception as exc:
        logger.error("create_session failed: %s", exc)
    return token


def _is_session_valid(created_at: str, last_activity: str) -> bool:
    """Return False if the session has exceeded absolute or idle timeout."""
    now = datetime.now(timezone.utc)
    try:
        ca = datetime.fromisoformat(created_at)
        la = datetime.fromisoformat(last_activity)
    except (TypeError, ValueError):
        return False
    if now - ca > timedelta(hours=SESSION_ABSOLUTE_HOURS):
        return False
    if now - la > timedelta(minutes=SESSION_IDLE_MINUTES):
        return False
    return True


def get_session(request: Request) -> dict | None:
    """Get the current session from the cookie via the database, or None."""
    token = request.cookies.get("session_token")
    if not token:
        return None
    from webapp.models import AppSession
    try:
        with _db() as session:
            row = session.query(AppSession).filter(AppSession.token == token).first()
            if not row:
                return None
            if not _is_session_valid(row.created_at, row.last_activity):
                session.delete(row)
                session.commit()
                return None
            # Bump last_activity on every valid access
            row.last_activity = datetime.now(timezone.utc).isoformat()
            session.commit()
            return {
                "email":         row.email,
                "name":          row.name,
                "role":          row.role,
                "csrf_token":    row.csrf_token,
                "created_at":    row.created_at,
                "last_activity": row.last_activity,
            }
    except Exception as exc:
        logger.error("get_session failed: %s", exc)
        return None


def destroy_session(request: Request):
    """Destroy the current session in the database."""
    token = request.cookies.get("session_token")
    if not token:
        return
    from webapp.models import AppSession
    try:
        with _db() as session:
            row = session.query(AppSession).filter(AppSession.token == token).first()
            if row:
                email = row.email
                session.delete(row)
                session.commit()
                logger.info("Session destroyed for %s", email)
    except Exception as exc:
        logger.error("destroy_session failed: %s", exc)


def require_auth(request: Request) -> dict | None:
    """Check if the request is authenticated.  Returns user dict or None."""
    return get_session(request)


def login_redirect() -> RedirectResponse:
    """Return a redirect to the login page."""
    return RedirectResponse(url="/login", status_code=302)


def get_auth_error(email: str) -> str:
    """Return a user-facing error message after a failed login attempt."""
    if is_account_locked(email.strip().lower()):
        return (
            f"Account temporarily locked due to too many failed attempts. "
            f"Please try again in {LOCKOUT_MINUTES} minutes."
        )
    return "Invalid email or password."


def get_login_activity() -> list[dict]:
    """Return the 50 most recent login audit log entries (newest first)."""
    from webapp.models import LoginAuditLog
    try:
        with _db() as session:
            rows = (
                session.query(LoginAuditLog)
                .order_by(LoginAuditLog.timestamp.desc())
                .limit(50)
                .all()
            )
            return [
                {
                    "timestamp":  r.timestamp,
                    "email":      r.user_email,
                    "name":       r.name,
                    "action":     r.action,
                    "ip_address": r.ip_address,
                    "user_agent": r.user_agent,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.error("get_login_activity failed: %s", exc)
        return []
