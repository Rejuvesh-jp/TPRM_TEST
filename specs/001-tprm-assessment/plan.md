# Implementation Plan: AI-Powered TPRM Assessment Platform

**Branch**: `001-tprm-assessment` | **Date**: 2026-03-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-tprm-assessment/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Build an AI-powered Third Party Risk Management (TPRM) assessment system that evaluates vendor risk posture using SIG Lite questionnaires, uploaded artifacts, internal policies, and contract clauses. The system will use a Retrieval-Augmented Generation (RAG) architecture to cross-reference claims against evidence, identify compliance gaps, and generate risk assessments with remediation recommendations.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI (Backend), OpenAI API (LLM/Embeddings), Celery (Workers), Redis (Queue), Pydantic (Validation), SQLAlchemy (ORM)
**Storage**: PostgreSQL 15+ with pgvector extension (Relational + Vector Store)
**Testing**: pytest (Unit/Integration), httpx (API tests)
**Target Platform**: Internal enterprise deployment (Docker/Kubernetes)
**Project Type**: AI-assisted document analysis and risk reasoning platform (Microservices-based)
**Performance Goals**: <60s questionnaire analysis, <30s per artifact processing, support 10+ concurrent assessments
**Constraints**: Deterministic processing pipeline, strict source attribution for AI outputs, role-based access control
**Scale/Scope**: Enterprise scale, supporting large artifact archives (ZIPs) and high document volume

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Modular AI Microservices
- **Pass**: Architecture defines clear services (Questionnaire, Artifact, Risk, etc.) with loose coupling as required.

### II. Retrieval-Augmented Generation (RAG)
- **Pass**: System design explicitly enforces retrieving relevant context (artifacts, policies) via vector search before LLM reasoning.

### III. Cost and Rate Limit Optimization
- **Pass**: Plan includes embedding reuse, caching, batching, and exponential backoff strategies.

### IV. Document Processing Pipeline
- **Pass**: Artifacts follow the strict extraction → chunking → embedding → storage → insight generation pipeline.

### VIII. Data Persistence
- **Pass**: PostgreSQL is the single source of truth for all intermediate and final outputs; no in-memory storage for assessment data.

### IX. API Design Standards
- **Pass**: All capabilities exposed via FastAPI REST endpoints with async support for long-running tasks.

### X. Security and Compliance
- **Pass**: Includes API key protection, AI interaction logging, and data isolation per vendor.

### XV. Testing Requirements
- **Pass**: Plan includes unit, integration, API, and LLM evaluation tests.

## Project Structure

### Documentation (this feature)

```text
specs/001-tprm-assessment/
├── plan.md              # This file
├── research.md          # Technology decisions and RAG strategy
├── data-model.md        # Database schema and entity relationships
├── quickstart.md        # User guide for API interaction
└── checklists/          # Quality assurance checklists
```

### Source Code (repository root)

```text
app/
├── api/                 # FastAPI route handlers
│   ├── v1/
│   │   ├── analysis.py
│   │   ├── artifacts.py
│   │   ├── assessments.py
│   │   └── questionnaires.py
│   └── dependencies.py
├── core/                # Configuration and security
├── models/              # SQLAlchemy/pgvector models
├── schemas/             # Pydantic request/response models
├── services/            # Business logic domains
│   ├── artifact_service.py
│   ├── embedding_service.py
│   ├── gap_analysis_service.py
│   ├── questionnaire_service.py
│   ├── retrieval_service.py
│   └── risk_service.py
├── workers/             # Background task handlers (Celery)
│   ├── tasks.py
│   └── pipelines.py
└── utils/               # Shared utilities
    ├── chunking.py
    └── llm.py

tests/
├── unit/
├── integration/
├── api/
└── llm_eval/
```

**Structure Decision**: Modular service-based architecture within a single monorepo structure, using FastAPI for the API layer and Celery for asynchronous background processing, strictly adhering to Constitution Principle XIV.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

N/A - Compliant with all constitution principles.
