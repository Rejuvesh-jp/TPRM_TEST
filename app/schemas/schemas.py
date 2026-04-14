import uuid
from datetime import datetime
from pydantic import BaseModel, Field


# ─── Vendor ───────────────────────────────────────────────
class VendorCreate(BaseModel):
    name: str = Field(..., max_length=255)
    domain: str | None = Field(None, max_length=255)


class VendorResponse(BaseModel):
    id: uuid.UUID
    name: str
    domain: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Assessment ───────────────────────────────────────────
class AssessmentCreate(BaseModel):
    vendor_id: uuid.UUID


class AssessmentResponse(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AssessmentStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    stage: str | None = None
    progress: int | None = None


# ─── Questionnaire ────────────────────────────────────────
class QuestionnaireResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    file_name: str
    analysis_status: str
    analysis_result: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionResponse(BaseModel):
    id: uuid.UUID
    section: str
    control_id: str | None
    question_text: str
    response_text: str | None
    justification: str | None
    risk_relevance: str | None
    claim_strength: float | None
    flags: dict | None

    model_config = {"from_attributes": True}


# ─── Artifact ─────────────────────────────────────────────
class ArtifactResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    file_name: str
    file_type: str | None
    processing_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactInsightResponse(BaseModel):
    id: uuid.UUID
    artifact_id: uuid.UUID
    insight_type: str
    description: str
    confidence: float | None

    model_config = {"from_attributes": True}


# ─── Gap ──────────────────────────────────────────────────
class GapResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    question_id: uuid.UUID | None
    gap_type: str
    description: str
    severity: str
    source_refs: dict | None

    model_config = {"from_attributes": True}


# ─── Risk ─────────────────────────────────────────────────
class RiskResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    gap_id: uuid.UUID
    risk_level: str
    rationale: str
    remediation_plan: str | None
    status: str

    model_config = {"from_attributes": True}


# ─── Recommendation ──────────────────────────────────────
class RecommendationResponse(BaseModel):
    id: uuid.UUID
    risk_assessment_id: uuid.UUID
    clause_text: str
    justification: str

    model_config = {"from_attributes": True}


# ─── HITL ─────────────────────────────────────────────────
class HITLFeedbackCreate(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    modified_value: dict
    justification: str


class HITLFeedbackResponse(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    reviewer_id: str
    original_value: dict | None
    modified_value: dict | None
    justification: str
    timestamp: datetime

    model_config = {"from_attributes": True}


# ─── Policy ───────────────────────────────────────────────
class PolicyCreate(BaseModel):
    title: str = Field(..., max_length=255)
    version: str | None = None


class PolicyResponse(BaseModel):
    id: uuid.UUID
    title: str
    version: str | None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Contract Clause ─────────────────────────────────────
class ContractClauseCreate(BaseModel):
    category: str = Field(..., max_length=100)
    standard_clause: bool = True


class ContractClauseResponse(BaseModel):
    id: uuid.UUID
    category: str
    standard_clause: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Report ──────────────────────────────────────────────
class AssessmentReport(BaseModel):
    assessment: AssessmentResponse
    vendor: VendorResponse
    questionnaire_insights: list[QuestionnaireResponse] = []
    questions: list[QuestionResponse] = []
    artifacts: list[ArtifactResponse] = []
    artifact_insights: list[ArtifactInsightResponse] = []
    gaps: list[GapResponse] = []
    risks: list[RiskResponse] = []
    recommendations: list[RecommendationResponse] = []
    hitl_feedback: list[HITLFeedbackResponse] = []


# ─── Common ──────────────────────────────────────────────
class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    timestamp: datetime
