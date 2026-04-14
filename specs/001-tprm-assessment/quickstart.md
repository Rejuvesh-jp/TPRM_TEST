# Quickstart: TPRM Assessment Platform

**Feature**: `001-tprm-assessment`
**Date**: 2026-03-09

## Prerequisites

1. **Docker & Docker Compose**: Ensure you have Docker Desktop installed.
2. **OpenAI API Key**: Valid API key with GPT-4 and Embeddings access.
3. **PostgreSQL Client**: `psql` or a GUI like pgAdmin (optional).

## Setup

1. **Clone Repository**:
   ```bash
   git clone <repo-url>
   cd tprm-ai
   ```

2. **Environment Configuration**:
   Create a `.env` file in the root directory:
   ```env
   POSTGRES_USER=tprm_user
   POSTGRES_PASSWORD=secure_password
   POSTGRES_DB=tprm_db
   OPENAI_API_KEY=sk-...
   CELERY_BROKER_URL=redis://localhost:6379/0
   SECRET_KEY=dev_secret
   ```

3. **Build & Start Services**:
   ```bash
   docker-compose up --build -d
   ```
   This starts:
   - FastAPI Backend (Port 8000)
   - PostgreSQL + pgvector (Port 5432)
   - Redis (Port 6379)
   - Celery Worker (Background)

4. **Initialize Database**:
   ```bash
   docker-compose exec api alembic upgrade head
   ```
   (This runs migrations to create tables and vector indexes)

## Usage Guide

### 1. Upload a Questionnaire
**Endpoint**: `POST /api/v1/questionnaires/upload`
- **Body**: Multipart form-data with `file` (PDF) or `json_data`.
- **Response**: `{"id": "uuid", "status": "processing"}`

### 2. Upload Artifacts (Evidence)
**Endpoint**: `POST /api/v1/artifacts/upload/{assessment_id}`
- **Body**: Multipart form-data with `files` (List of PDF/DOCX/ZIP).
- **Response**: `{"uploaded_count": 5, "status": "queued"}`

### 3. Trigger Full Assessment
**Endpoint**: `POST /api/v1/assessments/{assessment_id}/run`
- **Actions**: Triggers question analysis -> artifact indexing -> gap analysis -> risk scoring.
- **Response**: `{"job_id": "uuid", "status": "started"}`

### 4. Check Status
**Endpoint**: `GET /api/v1/assessments/{assessment_id}/status`
- **Response**: `{"stage": "gap_analysis", "progress": 65}`

### 5. View Final Report
**Endpoint**: `GET /api/v1/assessments/{assessment_id}/report`
- **Response**: JSON object with Executive Summary, Gaps, Risks, and Recommendations.

## Troubleshooting

- **Logs**: `docker-compose logs -f api` or `docker-compose logs -f worker`
- **Worker Issues**: Ensure Redis is running. `docker-compose restart redis worker`
- **Database**: Connect via `psql -h localhost -U tprm_user -d tprm_db` to inspect `artifact_chunks` or `gap_assessments`.
