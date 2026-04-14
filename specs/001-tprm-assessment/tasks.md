---
description: "Task list for TPRM Assessment Platform implementation"
---

# Tasks: AI-Powered TPRM Assessment Platform

**Input**: Design documents from `/specs/001-tprm-assessment/`
**Prerequisites**: plan.md (required), spec.md (required), data-model.md
**Organization**: Tasks are grouped by implementation phase and user story priority.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel
- **[Story]**: User Story ID (e.g., US1, US2) from spec.md
- **File Paths**: Exact paths based on `app/` structure in plan.md

## Phase 1: Setup & Infrastructure (Shared)

**Purpose**: Initialize project, database, and background worker infrastructure.

- [ ] T001 Create project directory structure (app/, tests/, specs/)
- [ ] T002 Initialize Python project with Poetry/pip (FastAPI, SQLAlchemy, Celery, OpenAI)
- [ ] T003 Configure Docker Compose for PostgreSQL + pgvector, Redis, API, and Worker
- [ ] T004 Create core configuration module in `app/core/config.py` (Env vars, Secrets)
- [ ] T005 Setup database connection and session manager in `app/core/database.py`
- [ ] T006 [P] Configure logging and observability in `app/core/logging.py`
- [ ] T007 Configure Celery application and broker connection in `app/core/celery_app.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models, security, and shared utilities required by all features.

- [ ] T008 [DB] implement base SQLAlchemy models in `app/models/base.py`
- [ ] T009 [DB] Setup Alembic migrations and create initial revision
- [ ] T010 [DB] Enable `vector` extension in PostgreSQL migration
- [ ] T011 [Security] Implement RBAC middleware and dependency in `app/core/security.py`
- [ ] T012 [Security] Implement audit logging decorator/middleware for AI interactions
- [ ] T013 [Util] Implement OpenAI client wrapper with retry logic (exponential backoff) in `app/utils/llm.py`
- [ ] T014 [Util] Create prompt template manager in `app/utils/prompts.py` (load from file/DB)
- [ ] T015 [API] Setup FastAPI app, CORS, and V1 router in `app/main.py`

**Checkpoint**: Application can start, connect to DB/Redis, and exposes health check.

---

## Phase 3: User Story 1 — Upload and Analyze Questionnaire (Priority: P1)

**Goal**: Ingest SIG Lite PDF, parse structure, and generate AI insights.

### Database & Models
- [ ] T016 [US1] Create `Questionnaire`, `Question`, `Vendor` models in `app/models/`
- [ ] T017 [US1] Create migration for questionnaire tables

### Implementation
- [ ] T018 [US1] Implement PDF text extraction logic in `app/services/questionnaire_service.py`
- [ ] T019 [US1] Create structured prompt for questionnaire parsing in `app/prompts/questionnaire_parsing.yaml`
- [ ] T020 [US1] Create structured prompt for risk analysis in `app/prompts/questionnaire_analysis.yaml`
- [ ] T021 [US1] Implement `analyze_questionnaire` async task in `app/workers/tasks.py`
- [ ] T022 [US1] Implement API endpoint `POST /api/v1/questionnaires/upload`
- [ ] T023 [US1] Implement API endpoint `GET /api/v1/questionnaires/{id}` for status/results
- [ ] T024 [P] [US1] Unit tests for questionnaire parsing logic
- [ ] T025 [P] [US1] Integration test for full upload -> analysis flow

**Checkpoint**: Users can upload a PDF and get structured JSON analysis back.

---

## Phase 4: User Story 2 — Artifact Processing Pipeline (Priority: P1)

**Goal**: Ingest vendor artifacts (ZIP/PDF/DOCX), chunk, embed, and generate insights.

### Database & Models
- [ ] T026 [US2] Create `Artifact`, `ArtifactChunk`, `ArtifactInsight` models in `app/models/`
- [ ] T027 [US2] Create migration for artifact tables (with vector column)

### Implementation
- [ ] T028 [US2] Implement file extractor factory (PDF, DOCX, TXT, XLSX) in `app/utils/extraction.py`
- [ ] T029 [US2] Implement sliding window chunking logic in `app/utils/chunking.py`
- [ ] T030 [US2] Implement `EmbeddingService` for batch embedding generation in `app/services/embedding_service.py`
- [ ] T031 [US2] Implement embedding caching mechanism to avoid re-embedding same text
- [ ] T032 [US2] Create prompt for artifact insight extraction in `app/prompts/artifact_insight.yaml`
- [ ] T033 [US2] Implement `process_artifact_pipeline` task in `app/workers/pipelines.py`
- [ ] T034 [US2] Implement API endpoint `POST /api/v1/artifacts/upload/{assessment_id}`
- [ ] T035 [US2] Implement API endpoint `GET /api/v1/artifacts/{id}/insights`
- [ ] T036 [P] [US2] Unit tests for chunking and extraction modules

**Checkpoint**: Artifacts unzip, process, and vectors populate the DB.

---

## Phase 5: User Story 8 — Embed Policies & Contract Clauses (Priority: P1)

**Goal**: Ingest internal policies/contracts for RAG retrieval context.
*Note: Crucial dependency for Gap Analysis.*

### Database & Models
- [ ] T037 [US8] Create `Policy`, `ContractClause` models in `app/models/`
- [ ] T038 [US8] Create migration for policy/contract tables

### Implementation
- [ ] T039 [US8] Reuse artifact pipeline to implement `process_policy_document` task
- [ ] T040 [US8] Implement `VectorRetrievalService` for similarity search in `app/services/retrieval_service.py`
- [ ] T041 [US8] Implement API endpoints for uploading policies/contracts (`POST /api/v1/policies/upload`)
- [ ] T042 [P] [US8] Integration test for policy upload and vector retrieval accuracy

**Checkpoint**: Internal knowledge base is searchable via vector search.

---

## Phase 6: User Story 3 — Gap Analysis (Priority: P2)

**Goal**: Identify gaps by cross-referencing Questionnaire vs Artifacts vs Policies.

### Database & Models
- [ ] T043 [US3] Create `GapAssessment` model in `app/models/`
- [ ] T044 [US3] Create migration for gap assessment table

### Implementation
- [ ] T045 [US3] Create prompt for gap reasoning in `app/prompts/gap_analysis.yaml`
- [ ] T046 [US3] Implement `GapAnalysisService` orchestrating retrieval and reasoning
- [ ] T047 [US3] Implement RAG logic: Retrieve relevant chunks for each questionnaire response
- [ ] T048 [US3] Implement async task `run_gap_analysis` in `app/workers/tasks.py`
- [ ] T049 [US3] Update Assessment API to trigger gap analysis stage
- [ ] T050 [P] [US3] LLM evaluation test for gap detection accuracy (using synthetic test cases)

**Checkpoint**: System identifies missing evidence and policy violations.

---

## Phase 7: User Story 4 — Risk Assessment (Priority: P2)

**Goal**: Score identified gaps (Low/Med/High/Critical) and assign logic.

### Database & Models
- [ ] T051 [US4] Create `RiskAssessment` model in `app/models/`
- [ ] T052 [US4] Create migration for risk assessment table

### Implementation
- [ ] T053 [US4] Create prompt for risk scoring and severity analysis in `app/prompts/risk_assessment.yaml`
- [ ] T054 [US4] Implement `RiskService` to process Gap -> Risk transformation
- [ ] T055 [US4] Implement logic to map regulatory impact to risk scores
- [ ] T056 [US4] Integrate risk assessment step into the async pipeline
- [ ] T057 [US4] Implement API endpoint `GET /api/v1/assessments/{id}/risks`
- [ ] T058 [P] [US4] Unit tests for risk scoring logic

**Checkpoint**: Gaps are converted to scored risks.

---

## Phase 8: User Story 7 — Retrieve Assessment Report (Priority: P2)

**Goal**: Aggregate all insights into a final JSON report.

### Implementation
- [ ] T059 [US7] Implement `AssessmentService.get_full_report` to aggregate data
- [ ] T060 [US7] Design and implement JSON report structure (Executive Summary, Details, Appendices)
- [ ] T061 [US7] Ensure all AI outputs have source attribution (citations) included
- [ ] T062 [US7] Implement API endpoint `GET /api/v1/assessments/{id}/report`

**Checkpoint**: Full end-to-end report generation works.

---

## Phase 9: User Story 5 — Contract Clause Recommendations (Priority: P3)

**Goal**: Suggest specific contract language to mitigate risks.

### Database & Models
- [ ] T063 [US5] Create `Recommendation` model in `app/models/`
- [ ] T064 [US5] Create migration for recommendations

### Implementation
- [ ] T065 [US5] Create prompt for clause recommendation in `app/prompts/recommendation.yaml`
- [ ] T066 [US5] Implement retrieval logic for standard clauses based on risk type
- [ ] T067 [US5] Integrate recommendation generation into the assessment pipeline
- [ ] T068 [US5] Update report generation to include recommendations section

---

## Phase 10: User Story 6 — Human-in-the-Loop Review (Priority: P3)

**Goal**: Allow analysts to override AI findings.

### Database & Models
- [ ] T069 [US6] Create `HITLFeedback` model/table in `app/models/`
- [ ] T070 [US6] Create migration for feedback history

### Implementation
- [ ] T071 [US6] Implement service method to apply overrides to Risk/Gap records
- [ ] T072 [US6] Implement versioning/history tracking for overrides
- [ ] T073 [US6] Implement API endpoint `POST /api/v1/hitl/review`
- [ ] T074 [US6] Ensure report generation respects validated/overridden values
- [ ] T075 [P] [US6] Integration test for override persistence and report update

---

## Dependencies & Implementation Order

1. **Infrastructure**: Phase 1 & 2 MUST be completed first.
2. **Data Ingestion**: Phase 3 (Questionnaire) and Phase 4 (Artifacts) and Phase 5 (Policies) can run in parallel, but ALL must complete before Phase 6.
3. **Core Logic**: Phase 6 (Gap) -> Phase 7 (Risk) -> Phase 8 (Report) is a strict linear dependency.
4. **Enhancements**: Phase 9 (Recs) and Phase 10 (HITL) can be implemented last.

## Parallel Execution Opportunities

- **Front-End/API vs Worker**: Once API contracts are defined (Phase 2), API implementation can effectively run parallel to Worker task implementation.
- **Ingestion Pipelines**: The Questionnaire pipeline (US1) and Artifact pipeline (US2) are independent until the Gap Analysis stage.

## Implementation Strategy

1. **MVP**: Deliver Phase 1-4. This allows uploading data and seeing parsed results/embeddings.
2. **Alpha**: Deliver Phase 5-8. This completes the core "AI Assessment" loop.
3. **Beta**: Deliver Phase 9-10. Adds human review and recommendations for full utility.
