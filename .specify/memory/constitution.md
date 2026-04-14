<!--
  Sync Impact Report
  ==================
  Version change: N/A → 1.0.0 (initial ratification)
  Modified principles: N/A (initial creation)
  Added sections:
    - Core Principles (15 principles)
    - Technology Stack
    - Folder Structure
    - Testing Requirements
    - Governance
  Removed sections: N/A
  Templates requiring updates:
    - .specify/plan-template.md ⚠ pending (Constitution Check gates to be
      filled when first plan is created)
    - .specify/spec-template.md ⚠ pending (aligned in structure; no
      immediate changes required)
    - .specify/tasks-template.md ⚠ pending (task phases align; no
      immediate changes required)
  Follow-up TODOs: None
-->

# TPRM AI Platform Constitution

## Technology Stack

**Language**: Python 3.11+
**Backend Framework**: FastAPI
**Database**: PostgreSQL with pgvector extension
**LLM Provider**: OpenAI API
**Embedding Model**: OpenAI embeddings
**Application Type**: AI-assisted document analysis and risk reasoning
**Deployment Target**: Internal enterprise deployment
**Testing**: pytest

## Core Principles

### I. Modular AI Microservices

The system MUST be organized into clearly defined, independently
testable, and loosely coupled services:

- **Questionnaire Analysis Service** — parses and interprets SIG Lite
  questionnaire responses
- **Artifact Analysis Service** — extracts, chunks, embeds, and
  analyzes vendor-provided documents
- **Policy and Contract Embedding Service** — embeds internal security
  policies and contractual clauses for retrieval
- **Risk Assessment Service** — aggregates findings and produces
  scored risk assessments
- **Reasoning Engine** — orchestrates LLM-based reasoning over
  retrieved context
- **Retrieval Service** — performs vector similarity search against
  pgvector to surface relevant context
- **API Gateway** — exposes all capabilities via FastAPI REST
  endpoints
- **Database Layer** — manages PostgreSQL persistence including
  pgvector operations

Each service MUST have a defined interface boundary. No service may
directly access another service's database tables; all inter-service
communication MUST go through defined APIs or shared repository
abstractions.

### II. Retrieval-Augmented Generation (RAG)

All LLM reasoning MUST rely on retrieved context. The LLM MUST NOT
generate answers from parametric knowledge alone.

Retrieved context sources include:

- Questionnaire responses
- Artifact text chunks
- Internal security policies
- Contract clauses

Implementation requirements:

- Embeddings MUST be stored in PostgreSQL using the pgvector extension
- Vector similarity search MUST be used to retrieve relevant context
  before any LLM call
- Retrieved context MUST be included in the LLM prompt
- The system MUST NOT pass entire documents to the LLM; only relevant
  chunks identified via retrieval are permitted

### III. Cost and Rate Limit Optimization

The system MUST minimize OpenAI API usage through the following
mandatory techniques:

- **Embedding reuse**: Once generated, embeddings MUST be persisted
  and reused; re-embedding unchanged content is prohibited
- **LLM output caching**: Identical context + prompt combinations
  MUST return cached results when available
- **Efficient chunking**: Documents MUST be chunked using a
  consistent strategy (e.g., token-aware sliding window) to avoid
  unnecessarily large or small chunks
- **Batch embedding generation**: Multiple chunks MUST be embedded
  in a single API call where possible
- **Exponential backoff**: All OpenAI API calls MUST implement
  exponential backoff with jitter for rate limit handling
- **Deduplication**: The system MUST NOT make repeated LLM calls for
  the same context and prompt within a single assessment run

### IV. Document Processing Pipeline

Artifact processing MUST follow this deterministic pipeline in order:

1. Extract text from uploaded documents
2. Chunk text into manageable segments
3. Generate embeddings for each chunk
4. Store chunks and embeddings in PostgreSQL (pgvector)
5. Generate artifact insights via LLM reasoning over chunks
6. Store artifact insights in PostgreSQL
7. Retrieve relevant chunks using vector similarity search during
   assessment

Supported artifact formats MUST include at minimum:

- PDF
- DOCX
- TXT
- CSV
- XLSX
- JSON

All formats MUST be extracted to plain text before chunking. ZIP
archives containing multiple artifacts MUST be unpacked and each
contained file processed individually through the pipeline.

### V. AI Reasoning Transparency

All AI-generated outputs MUST include the following metadata for
auditability and compliance:

- **Source artifact references**: Which documents contributed to the
  output
- **Source questionnaire references**: Which questionnaire responses
  were used
- **Confidence indicators**: A structured confidence score or level
  for each conclusion
- **Explanation of reasoning**: A human-readable explanation of how
  the conclusion was reached

No AI output may be presented to users without accompanying source
attribution. This is NON-NEGOTIABLE for enterprise compliance.

### VI. Human-in-the-Loop Validation

The system MUST support human review at the following decision points:

- **Questionnaire analysis validation**: Reviewers MUST be able to
  approve, reject, or modify AI-interpreted questionnaire findings
- **Artifact interpretation validation**: Reviewers MUST be able to
  confirm or correct AI-extracted artifact insights
- **Risk assessment validation**: Reviewers MUST be able to override
  AI-assigned risk levels and modify recommendations

Human overrides MUST be recorded with:

- Reviewer identity
- Timestamp
- Original AI output
- Modified output
- Justification for override

The system MUST treat human-validated outputs as authoritative over
AI-generated outputs in all downstream processing.

### VII. Risk Assessment Framework

Every risk assessment MUST evaluate and report on:

- **Identified gaps**: Missing controls or processes
- **Missing controls**: Security controls required but not evidenced
- **Weak policy evidence**: Policies referenced but insufficiently
  supported by artifacts
- **Contractual misalignment**: Gaps between contractual obligations
  and demonstrated vendor capabilities

Each identified risk MUST include:

- **Risk level**: One of Low, Medium, High, or Critical
- **Supporting evidence**: References to specific questionnaire
  responses, artifact chunks, or policy sections
- **Recommended remediation**: Actionable steps to address the risk

Risk levels MUST be consistently applied using a defined rubric. The
rubric MUST be version-controlled and auditable.

### VIII. Data Persistence

All intermediate and final outputs MUST be stored in PostgreSQL.
In-memory-only storage for assessment data is prohibited.

Persisted data MUST include:

- Questionnaire analysis results
- Artifact text chunks
- Embeddings (via pgvector)
- Artifact insights
- Risk assessments
- AI reasoning outputs (prompts, responses, metadata)
- Human review decisions

Every persisted record MUST include created/updated timestamps and
a reference to the assessment run that produced it.

### IX. API Design Standards

All system capabilities MUST be exposed via REST APIs using FastAPI.

Required API endpoints:

- **Upload Questionnaire** — accept and store SIG Lite questionnaire
- **Upload Artifacts** — accept ZIP or individual files
- **Run Questionnaire Analysis** — trigger analysis pipeline
- **Run Artifact Analysis** — trigger document processing pipeline
- **Run Risk Assessment** — trigger full risk assessment
- **Retrieve Assessment Report** — return completed assessment
- **Human Review Input** — accept reviewer feedback and overrides

API requirements:

- All long-running operations MUST support asynchronous processing
  (e.g., background tasks with status polling)
- All endpoints MUST return structured JSON responses
- All endpoints MUST include appropriate HTTP status codes
- Request/response models MUST be defined using Pydantic
- API documentation MUST be auto-generated via FastAPI OpenAPI

### X. Security and Compliance

The system MUST enforce the following security controls:

- **API key protection**: All API keys (OpenAI, internal) MUST be
  loaded from environment variables or a secrets manager; hardcoded
  keys are prohibited
- **Data minimization for LLM**: Only the minimum necessary context
  MUST be sent to the LLM; full documents or sensitive PII MUST NOT
  be included unless strictly required
- **AI interaction logging**: Every LLM call MUST be logged with
  timestamp, prompt hash, token usage, and response metadata for
  traceability
- **Encryption**: Sensitive stored data MUST be encrypted at rest
  when required by enterprise policy
- **Access control**: API endpoints MUST enforce authentication and
  authorization appropriate to the deployment environment

### XI. Performance and Scalability

The system MUST be optimized for enterprise-scale workloads:

- **Large uploads**: The system MUST handle ZIP archives containing
  50+ documents without timeout or memory exhaustion
- **Parallel processing**: Artifact extraction and embedding
  generation MUST support parallel execution
- **Batch embeddings**: Embedding API calls MUST be batched to
  minimize round trips
- **Background workers**: Long-running tasks (analysis, embedding,
  assessment) MUST execute in background workers, not in request
  handlers
- **Streaming responses**: Where applicable, API responses SHOULD
  support streaming for large result sets

### XII. Observability

The system MUST implement comprehensive observability:

- **Structured logging**: All log output MUST use structured JSON
  format with consistent fields (timestamp, service, level, message,
  correlation_id)
- **Request tracing**: Every API request MUST carry a correlation ID
  propagated through all downstream service calls
- **AI call monitoring**: LLM API calls MUST be tracked with token
  usage, latency, and error rates
- **Error tracking**: All exceptions MUST be captured with full
  context and stack traces

### XIII. Code Quality Standards

All code MUST adhere to:

- **Clean architecture**: Business logic MUST be separated from
  framework concerns; services MUST NOT contain FastAPI-specific code
- **Type hints**: All function signatures MUST include type
  annotations; mypy or equivalent static analysis SHOULD pass
  without errors
- **Modular service structure**: Each service MUST reside in its own
  module with a defined public interface
- **Linting**: Code MUST pass ruff or equivalent linter with zero
  warnings

### XIV. Folder Structure

The project MUST follow this modular structure:

```text
app/
├── api/            # FastAPI route handlers and request/response models
├── services/       # Business logic services (one per domain concern)
├── models/         # SQLAlchemy/Pydantic models and database schemas
├── repositories/   # Data access layer (PostgreSQL, pgvector queries)
├── workers/        # Background task definitions (Celery, asyncio, etc.)
└── utils/          # Shared utilities (chunking, embedding helpers, etc.)

tests/
├── unit/           # Unit tests for individual services and utilities
├── integration/    # Integration tests for pipelines and workflows
├── api/            # API endpoint tests
└── llm/            # LLM prompt evaluation tests
```

No business logic may reside in `api/` or `utils/`. Route handlers
in `api/` MUST delegate to services. Data access in services MUST
go through repositories.

### XV. Testing Requirements

The system MUST include the following test categories:

- **Unit tests**: Every service MUST have corresponding unit tests
  covering core logic, edge cases, and error handling
- **Integration tests**: End-to-end pipeline tests (upload →
  analysis → assessment) MUST verify correct data flow
- **API tests**: Every API endpoint MUST have tests covering success
  cases, validation errors, and authorization
- **LLM prompt evaluation tests**: Prompt templates MUST be tested
  against representative inputs to verify output quality and
  consistency

Test execution MUST be automated and runnable via `pytest`. Tests
MUST NOT require live OpenAI API access; LLM calls MUST be mocked
in unit and integration tests.

## Governance

This constitution is the authoritative reference for all architectural
and engineering decisions in the TPRM AI Platform. It supersedes
informal conventions, ad-hoc decisions, and undocumented practices.

### Compliance

- All pull requests MUST be verified against this constitution before
  merge
- Any deviation from a MUST requirement requires explicit
  justification documented in the PR description
- Code reviews MUST include a constitution compliance check

### Amendments

- Amendments to this constitution require:
  1. A written proposal describing the change and rationale
  2. Review and approval by the technical lead
  3. A migration plan for existing code affected by the change
  4. Version increment following semantic versioning:
     - MAJOR: Removal or redefinition of existing principles
     - MINOR: Addition of new principles or material expansion
     - PATCH: Clarifications, wording fixes, non-semantic refinements
- All amendments MUST update the version and Last Amended date below

### Complexity Justification

- Any architectural decision that introduces complexity beyond what
  this constitution prescribes MUST be justified in writing
- "We might need it later" is not a valid justification; YAGNI
  applies unless a concrete requirement exists

**Version**: 1.0.0 | **Ratified**: 2026-03-09 | **Last Amended**: 2026-03-09
