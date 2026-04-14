"""
Database Models
===============
SQLAlchemy ORM models for the TPRM assessment platform.
Uses pgvector for embedding storage and similarity search.
"""
import uuid
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

def _to_ist(iso_str: str | None) -> str | None:
    """Convert a UTC ISO timestamp string to IST (UTC+5:30)."""
    if not iso_str:
        return iso_str
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_IST).isoformat()
    except Exception:
        return iso_str

from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, ForeignKey, Index,
    LargeBinary,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pgvector.sqlalchemy import Vector

from webapp.db import Base

EMBEDDING_DIM = 1536


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_name: Mapped[str] = mapped_column(String(500), nullable=False)
    vendor_id: Mapped[str | None] = mapped_column(String(20), nullable=True)   # e.g. VND-A3F2B1
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default="1")
    division: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nature_of_engagement: Mapped[str | None] = mapped_column(String(20), nullable=True)  # high / medium / low
    pre_assessment_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"responses": [...], "total_score": N}
    spoc_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_email: Mapped[str | None] = mapped_column(String(200), nullable=True)  # email of the user who created this assessment
    risk_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)  # high / medium / low â€” manually assigned
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    use_openai: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    report_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    files = relationship("AssessmentFile", back_populates="assessment", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="assessment", cascade="all, delete-orphan")
    pipeline_outputs = relationship("PipelineOutput", back_populates="assessment", cascade="all, delete-orphan")

    def to_meta(self) -> dict:
        """Convert to the metadata dict format used by the rest of the app."""
        return {
            "id": self.id,
            "vendor_name": self.vendor_name,
            "vendor_id": self.vendor_id or "",
            "version": self.version if self.version is not None else 1,
            "division": self.division or "",
            "nature_of_engagement": self.nature_of_engagement or "",
            "pre_assessment_scores": self.pre_assessment_scores,
            "spoc_email": self.spoc_email or "",
            "created_by_email": self.created_by_email or "",
            "risk_rating": self.risk_rating or "",
            "status": self.status,
            "use_openai": self.use_openai,
            "created_at": _to_ist(self.created_at),
            "started_at": _to_ist(self.started_at),
            "completed_at": _to_ist(self.completed_at),
            "error": self.error,
            "progress": self.progress or {"current_step": 0, "total_steps": 7, "step_label": ""},
            "summary": self.summary,
        }


class AssessmentFile(Base):
    __tablename__ = "assessment_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    assessment = relationship("Assessment", back_populates="files")


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    store_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_document: Mapped[str | None] = mapped_column(String(500), nullable=True)
    chunk_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    assessment = relationship("Assessment", back_populates="embeddings")

    __table_args__ = (
        Index("ix_embeddings_assessment_store", "assessment_id", "store_name"),
    )


class PipelineOutput(Base):
    __tablename__ = "pipeline_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    output_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    assessment = relationship("Assessment", back_populates="pipeline_outputs")

    __table_args__ = (
        Index("ix_pipeline_output_assessment_step", "assessment_id", "step_name", unique=True),
    )


class DefaultDocument(Base):
    """Pre-loaded policies and contract clause files that are reused across assessments.
    Stores the file binary + pre-computed processed data (with embeddings) so
    they don't need to be re-embedded on every run.
    Supports versioning: each upload creates a new version; only the active version is used."""
    __tablename__ = "default_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "policies" or "contract_clauses"
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version_label: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    processed_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # pre-computed output with embeddings
    uploaded_at: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        Index("ix_default_docs_category_active", "category", "is_active"),
    )


# â”€â”€ User / Session / Audit tables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AppUser(Base):
    """Application users stored in the database (replaces config/users.json)."""
    __tablename__ = "app_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="analyst")
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(50), nullable=False)

    sessions = relationship("AppSession", back_populates="user",
                            cascade="all, delete-orphan")
    audit_logs = relationship("LoginAuditLog", back_populates="user",
                              cascade="all, delete-orphan",
                              foreign_keys="LoginAuditLog.user_email",
                              primaryjoin="AppUser.email == LoginAuditLog.user_email")


class AppSession(Base):
    """Persistent database-backed sessions (replaces _sessions in-memory dict)."""
    __tablename__ = "app_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_users.id", ondelete="CASCADE"),
                                         nullable=False)
    # Denormalised fields copied at session creation for fast lookups without joins
    email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    last_activity: Mapped[str] = mapped_column(String(50), nullable=False)

    user = relationship("AppUser", back_populates="sessions")


class LoginAuditLog(Base):
    """Login audit log stored in the database (replaces config/login_activity.json)."""
    __tablename__ = "login_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)   # LOGIN_SUCCESS / LOGIN_FAILED
    ip_address: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown")
    user_agent: Mapped[str] = mapped_column(String(200), nullable=False, default="Unknown")

    user = relationship("AppUser", back_populates="audit_logs",
                        foreign_keys=[user_email],
                        primaryjoin="AppUser.email == LoginAuditLog.user_email")

