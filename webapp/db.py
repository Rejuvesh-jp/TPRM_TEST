"""
Database Module
===============
Synchronous PostgreSQL connection via SQLAlchemy + pgvector.
The pipeline runs in a background thread, so we use sync sessions.
"""
import os
import logging
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from pgvector.sqlalchemy import Vector  # noqa: F401 — registers the type

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger("tprm.db")

# ── Build connection URL from .env ───────────────────────
_user = os.getenv("POSTGRES_USER", "tprm_user")
_password = quote_plus(os.getenv("POSTGRES_PASSWORD", ""))
_host = os.getenv("POSTGRES_HOST", "127.0.0.1")
_port = os.getenv("POSTGRES_PORT", "5432")
_db = os.getenv("POSTGRES_DB", "tprm_db")

DATABASE_URL = (
    f"postgresql+psycopg2://{_user}:{_password}@{_host}:{_port}/{_db}"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    # pool_recycle closes connections after 30 min, preventing stale-connection
    # errors without the SELECT 1 ping on every checkout (pool_pre_ping overhead).
    pool_recycle=1800,
)

SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_session():
    """Get a new sync DB session (use as context manager)."""
    return SessionLocal()


def init_db():
    """Create all tables, add new columns if missing, and backfill vendor versioning."""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    # Import models so they're registered with Base.metadata
    from webapp import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # ── Add vendor_id / version columns to existing tables (idempotent) ──────
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS vendor_id VARCHAR(20)"
        ))
        conn.execute(text(
            "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1"
        ))
        conn.execute(text(
            "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS division VARCHAR(200)"
        ))
        conn.execute(text(
            "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS nature_of_engagement VARCHAR(20)"
        ))
        conn.execute(text(
            "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS spoc_email VARCHAR(200)"
        ))
        conn.execute(text(
            "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS risk_rating VARCHAR(20)"
        ))
        conn.execute(text(
            "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS pre_assessment_scores JSONB"
        ))
        conn.execute(text(
            "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS created_by_email VARCHAR(200)"
        ))
        conn.commit()

    # ── Backfill vendor_id for rows that don't have one yet ──────────────────
    # vendor_id = 'VND-' + upper(left(md5(lower(trim(vendor_name))), 6))
    # This is the same formula used by create_assessment so they always match.
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE assessments
            SET vendor_id = 'VND-' || upper(left(md5(lower(trim(vendor_name))), 6))
            WHERE vendor_id IS NULL
        """))
        # ── Assign version numbers per vendor (ordered by created_at) ────────
        # Uses a window function so Definitive gets v1, and a second Definitive
        # assessment (if it existed) would get v2, etc.
        conn.execute(text("""
            UPDATE assessments a
            SET version = sub.rn
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY lower(trim(vendor_name))
                           ORDER BY created_at ASC
                       ) AS rn
                FROM assessments
            ) sub
            WHERE a.id = sub.id
        """))
        conn.commit()

    logger.info("Database tables created / verified")


def seed_users_from_json() -> int:
    """One-time migration: import users from config/users.json into app_users table.

    Safe to call on every startup — already-migrated users are skipped (upsert by email).
    Returns the number of new rows inserted.
    """
    import json
    from pathlib import Path
    from datetime import datetime, timezone

    users_file = Path(__file__).resolve().parent.parent / "config" / "users.json"
    if not users_file.exists():
        return 0

    try:
        raw = json.loads(users_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("seed_users_from_json: could not read users.json — %s", exc)
        return 0

    if not isinstance(raw, list) or not raw:
        return 0

    from webapp.models import AppUser
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    with SessionLocal() as session:
        for entry in raw:
            email = (entry.get("email") or "").strip().lower()
            if not email:
                continue
            exists = session.execute(
                text("SELECT 1 FROM app_users WHERE lower(email) = :e"),
                {"e": email},
            ).first()
            if exists:
                continue
            import uuid
            user = AppUser(
                id=str(uuid.uuid4()),
                email=entry["email"].strip(),
                name=entry.get("name", ""),
                role=entry.get("role", "analyst"),
                password_hash=entry.get("password_hash") or entry.get("password", ""),
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            inserted += 1
        session.commit()

    if inserted:
        logger.info("seed_users_from_json: migrated %d user(s) from users.json → app_users", inserted)
    return inserted


def seed_audit_from_json() -> int:
    """One-time migration: import login_activity.json into login_audit_logs table.

    Safe to call on every startup — duplicate timestamps + email combos are skipped.
    Returns the number of new rows inserted.
    """
    import json
    from pathlib import Path

    activity_file = Path(__file__).resolve().parent.parent / "config" / "login_activity.json"
    if not activity_file.exists():
        return 0

    try:
        raw = json.loads(activity_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("seed_audit_from_json: could not read login_activity.json — %s", exc)
        return 0

    if not isinstance(raw, list) or not raw:
        return 0

    from webapp.models import LoginAuditLog
    inserted = 0
    with SessionLocal() as session:
        for entry in raw:
            ts    = entry.get("timestamp", "")
            email = (entry.get("email") or "").strip().lower()
            if not ts or not email:
                continue
            exists = session.execute(
                text("SELECT 1 FROM login_audit_logs WHERE timestamp = :t AND lower(user_email) = :e"),
                {"t": ts, "e": email},
            ).first()
            if exists:
                continue
            import uuid
            log = LoginAuditLog(
                id=str(uuid.uuid4()),
                timestamp=ts,
                user_email=entry.get("email", ""),
                name=entry.get("name", ""),
                action=entry.get("action", "LOGIN_FAILED"),
                ip_address=entry.get("ip_address", "unknown"),
                user_agent=(entry.get("user_agent") or "Unknown")[:200],
            )
            session.add(log)
            inserted += 1
        session.commit()

    if inserted:
        logger.info("seed_audit_from_json: migrated %d log entries from login_activity.json → login_audit_logs", inserted)
    return inserted
