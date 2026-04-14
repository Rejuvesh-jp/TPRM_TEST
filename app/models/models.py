import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime, Enum, ForeignKey, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Vendor(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False
    )

    assessments = relationship("Assessment", back_populates="vendor", lazy="selectin")


class Assessment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "assessments"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), default="draft", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    vendor = relationship("Vendor", back_populates="assessments")
    questionnaires = relationship("Questionnaire", back_populates="assessment", lazy="selectin")
    artifacts = relationship("Artifact", back_populates="assessment", lazy="selectin")
    gap_assessments = relationship("GapAssessment", back_populates="assessment", lazy="selectin")
    risk_assessments = relationship("RiskAssessment", back_populates="assessment", lazy="selectin")


class Questionnaire(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "questionnaires"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=True)
    parsed_content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analysis_status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )
    analysis_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    assessment = relationship("Assessment", back_populates="questionnaires")
    questions = relationship("Question", back_populates="questionnaire", lazy="selectin")


class Question(UUIDMixin, Base):
    __tablename__ = "questions"

    questionnaire_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questionnaires.id"), nullable=False
    )
    section: Mapped[str] = mapped_column(String(255), nullable=False)
    control_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_relevance: Mapped[str | None] = mapped_column(String(20), nullable=True)
    expected_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    questionnaire = relationship("Questionnaire", back_populates="questions")


class Artifact(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(50), default="uploaded", nullable=False
    )
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    assessment = relationship("Assessment", back_populates="artifacts")
    chunks = relationship("ArtifactChunk", back_populates="artifact", lazy="selectin")
    insights = relationship("ArtifactInsight", back_populates="artifact", lazy="selectin")


class ArtifactChunk(UUIDMixin, Base):
    __tablename__ = "artifact_chunks"

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    artifact = relationship("Artifact", back_populates="chunks")


class ArtifactInsight(UUIDMixin, Base):
    __tablename__ = "artifact_insights"

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=False
    )
    insight_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_chunks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    artifact = relationship("Artifact", back_populates="insights")


class Policy(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "policies"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ContractClause(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "contract_clauses"

    category: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    standard_clause: Mapped[bool] = mapped_column(Boolean, default=True)


class GapAssessment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "gap_assessments"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id"), nullable=False
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id"), nullable=True
    )
    gap_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    source_refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    assessment = relationship("Assessment", back_populates="gap_assessments")
    risk_assessment = relationship("RiskAssessment", back_populates="gap", uselist=False)


class RiskAssessment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "risk_assessments"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id"), nullable=False
    )
    gap_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gap_assessments.id"), nullable=False
    )
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    remediation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")

    assessment = relationship("Assessment", back_populates="risk_assessments")
    gap = relationship("GapAssessment", back_populates="risk_assessment")
    recommendations = relationship("Recommendation", back_populates="risk_assessment", lazy="selectin")


class Recommendation(UUIDMixin, Base):
    __tablename__ = "recommendations"

    risk_assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("risk_assessments.id"), nullable=False
    )
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)

    risk_assessment = relationship("RiskAssessment", back_populates="recommendations")


class HITLFeedback(UUIDMixin, Base):
    __tablename__ = "hitl_feedback"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    original_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    modified_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
