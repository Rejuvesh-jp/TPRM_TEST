# TPRM AI Assessment Platform — Architecture

> **Purpose**: Comprehensive technical architecture document for MCP/Claude Cowork integration.
> **Last analysed**: May 2026

---

## 1. Application Overview

The **TPRM AI Assessment Platform** is an enterprise third-party risk management (TPRM) system built for **Titan Company Limited**. It automates vendor security assessments using a multi-step AI pipeline that parses SIG Lite questionnaires, extracts evidence from vendor artifacts (certificates, audit reports, policies), performs gap analysis against internal policies and contract clauses, scores risks, generates remediation plans, and produces downloadable PDF/Word reports — all without manual analyst effort.

**Version**: 1.0.0  
**Entry point (web)**: `webapp/main.py` → `uvicorn webapp.main:app --port 8085`  
**Entry point (core API)**: `app/main.py` → FastAPI at `/api/v1/*`

---

## 2. Core Business Purpose

| Goal | How the platform achieves it |
|------|------------------------------|
| Vendor risk scoring | 10-question Pre-Business Assessment (PBA) scores sensitivity: low / medium / high |
| Compliance gap identification | RAG-powered cross-reference of questionnaire answers vs artifacts, policies, clauses |
| Remediation planning | LLM generates one actionable remediation per gap with timeline, owner, acceptance criteria |
| Risk rating | LLM assigns risk level per gap; rolls up to overall vendor risk rating |
| Report generation | PDF and Word reports with executive summary, gap tables, remediation plans |
| Audit trail | Every login, assessment action, and HITL feedback is persisted in the database |
| Human-in-the-loop (HITL) | Reviewers can override AI outputs with justification; tracked in `hitl_feedback` table |

---

## 3. Technology Stack

### Backend
| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI 0.115.6 |
| ASGI server | Uvicorn 0.34.0 |
| ORM | SQLAlchemy 2.0 (async + sync) |
| Database | PostgreSQL 16 + pgvector extension |
| DB migrations | Alembic |
| AI / LLM | OpenAI API (`gpt-4` / `gpt-5.4-azure`) via Titan AI Gateway |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dim) |
| Document parsing | PyMuPDF, PyPDF, python-docx, openpyxl |
| OCR | pytesseract (Linux/Mac) / Windows OCR (Windows) |
| Rate limiting | slowapi |
| Auth (SSO) | MSAL (Microsoft Authentication Library) |
| Password hashing | bcrypt (work factor 12) |
| Report output | python-docx (Word), ReportLab (PDF) |

### Frontend
| Layer | Technology |
|-------|-----------|
| Template engine | Jinja2 |
| CSS framework | Bootstrap (via CDN) |
| Charts | Chart.js |
| Fonts | Google Fonts |
| Static files | FastAPI StaticFiles mount at `/static` |

### Infrastructure
| Component | Technology |
|-----------|-----------|
| Container runtime | Docker + Docker Compose |
| Database container | `pgvector/pgvector:pg16` |
| Cache (optional) | Redis 7 (Alpine) |
| Reverse proxy (prod) | Not included — expects a front-end proxy |
| Deployment | `docker-compose.prod.yml` |

---

## 4. Dual-Application Architecture

The codebase contains **two separate FastAPI applications** that serve different audiences:

### `webapp/` — User-Facing Web Application (Port 8085)
- Jinja2 HTML templates + REST API endpoints for the browser UI
- Session-based authentication (cookie + DB sessions)
- Azure AD SSO via MSAL
- All assessment CRUD, file upload, pipeline triggering, report download
- Admin user management

### `app/` — Core Processing API (Internal)
- Pure REST API (`/api/v1/*`) — no HTML templates
- `X-API-Key` header authentication
- Async SQLAlchemy sessions for high throughput
- Routes: `questionnaires`, `artifacts`, `assessments`, `policies`, `hitl`
- Intended for programmatic/MCP integration

---

## 5. Module / Folder Structure

```
TPRM_TEST/
├── app/                        # Core FastAPI API (internal/programmatic use)
│   ├── main.py                 # FastAPI app factory, router mounts
│   ├── api/v1/                 # Route handlers (questionnaires, artifacts, assessments, policies, hitl)
│   ├── core/                   # Config, database engines, security, logging
│   ├── models/                 # SQLAlchemy ORM models (app-layer schema)
│   ├── prompts/                # YAML LLM prompt templates (7 prompts)
│   ├── schemas/                # Pydantic request/response schemas
│   ├── services/               # Business logic (artifact, embedding, gap, questionnaire, retrieval, risk)
│   ├── utils/                  # Chunking, extraction, LLM call wrapper, prompt renderer
│   └── workers/                # Sync task runners (parse_questionnaire, process_artifact, gap, risk)
│
├── webapp/                     # User-facing web application (port 8085)
│   ├── main.py                 # FastAPI app with middleware stack, lifespan
│   ├── auth.py                 # Session auth, bcrypt, lockout, audit logging
│   ├── config.py               # App config from .env (SSO, feature flags, ports)
│   ├── db.py                   # Sync SQLAlchemy engine, Base, init_db()
│   ├── db_storage.py           # Assessment CRUD against PostgreSQL
│   ├── gateway_token.py        # Titan AI Gateway token (client credentials OAuth2)
│   ├── limiter.py              # slowapi rate limiter instance
│   ├── models.py               # SQLAlchemy ORM models (webapp-layer schema)
│   ├── obo_token.py            # On-behalf-of token flow (legacy)
│   ├── pg_vector_store.py      # pgvector-backed embedding store
│   ├── pipeline_runner.py      # 7-step assessment pipeline (background thread)
│   ├── report_generator.py     # PDF + Word report generation
│   ├── settings_store.py       # Runtime feature flags (JSON file + env vars)
│   ├── storage.py              # (legacy) file-based storage shim
│   ├── routes/
│   │   ├── api.py              # JSON REST endpoints (/api/*)
│   │   ├── pages.py            # HTML page routes (dashboard, assessment detail, analytics)
│   │   ├── sso.py              # Azure AD SSO routes (/auth/login, /auth/callback, /auth/logout)
│   │   └── user_management.py  # Admin user CRUD
│   ├── templates/              # Jinja2 HTML templates (13 templates)
│   └── static/                 # CSS, JS, images, vendor libraries
│
├── services/                   # Shared processing services (used by pipeline_runner)
│   ├── ocr_service.py          # PDF/DOCX/XLSX text extraction + OCR fallback
│   ├── questionnaire_parser.py # SIG Lite PDF parser (21 sections, 300+ questions)
│   ├── artifact_processor.py   # Chunk + embed vendor artifacts
│   ├── policy_processor.py     # Chunk + embed internal policies
│   ├── clause_processor.py     # Chunk + embed contract clauses
│   ├── embedding_service.py    # OpenAI embeddings + in-memory + DB cache
│   ├── gap_analysis_service.py # RAG gap identification (vs artifacts, policies, clauses)
│   ├── risk_assessment_service.py # LLM risk scoring per gap
│   ├── remedial_plan_service.py   # LLM remediation action generation
│   ├── recommendation_service.py  # RAG + LLM contract clause recommendations
│   ├── llm_judge.py            # Multi-pass LLM review/quality control
│   ├── llm_cache.py            # Two-tier LLM response cache (memory + DB)
│   └── assessment_fingerprint.py  # SHA-256 fingerprint for version-level caching
│
├── alembic/                    # Database migration scripts
├── config/                     # Runtime config files (users.json, pipeline_settings.json)
├── data/                       # Persisted assessment data
├── inputs/                     # Default policies, contract clauses, questionnaires
├── scripts/                    # DB setup, pipeline scripts, server setup
├── docs/                       # Setup documentation
├── docker-compose.yml          # Dev compose (DB + Redis)
├── docker-compose.prod.yml     # Production compose (DB + App)
├── Dockerfile                  # Application container image
└── requirements.txt            # Python dependencies
```

---

## 6. Data Flow Between Modules

```
User (Browser)
    │
    ▼
webapp/routes/api.py  ──────────────────────────────────────────────────────
    │  POST /api/assessments                                                 │
    │  • Validates files (MIME type, extension, size)                        │
    │  • Saves files to DB (assessment_files table)                          │
    │  • Creates assessment record (assessments table)                       │
    │  • Spawns background thread: pipeline_runner.run_pipeline_async()      │
    │                                                                        │
    ▼                                                                        │
webapp/pipeline_runner.py (background thread)                               │
    │                                                                        │
    ├─ Step 1: Score Pre-Business Assessment (10 yes/no questions → sensitivity)
    │                                                                        │
    ├─ Step 2: OCR / Extract text from all uploaded files                   │
    │          services/ocr_service.py                                       │
    │                                                                        │
    ├─ Step 3: Parse SIG Lite questionnaire                                 │
    │          services/questionnaire_parser.py                              │
    │          → extracts 300+ Q&A pairs, builds embeddings                  │
    │          services/embedding_service.py (OpenAI / mock)                 │
    │                                                                        │
    ├─ Step 4: Process artifacts (chunk + embed vendor documents)           │
    │          services/artifact_processor.py                                │
    │          → chunks stored in embeddings table (pgvector)                │
    │          webapp/pg_vector_store.py                                     │
    │                                                                        │
    ├─ Step 5: Load default policies and contract clauses                   │
    │          services/policy_processor.py                                  │
    │          services/clause_processor.py                                  │
    │          → loaded from DB (default_documents table)                    │
    │                                                                        │
    ├─ Step 6: Gap Analysis (RAG + LLM)                                     │
    │          services/gap_analysis_service.py                              │
    │          • RAG: cosine similarity search (questions vs chunks)         │
    │          • RAG: policy context retrieval                               │
    │          • RAG: contract clause context retrieval                      │
    │          • LLM: identifies gaps from combined evidence                 │
    │          • LLM: risk assessment per gap                                │
    │          • LLM: remedial plan per gap                                  │
    │          • LLM: contract clause recommendations                        │
    │                                                                        │
    ├─ Step 7: LLM Judge (optional, multi-pass quality review)              │
    │          services/llm_judge.py                                         │
    │          • Reviews draft output for duplicates, severity, wording      │
    │          • Returns corrections applied iteratively (up to 3 passes)    │
    │                                                                        │
    └─ Save final output to DB:                                              │
       • pipeline_outputs table (full JSON)                                  │
       • assessments.summary (gap count, risk rating, key metrics)           │
       • assessments.report_data (full report payload)                       │
                                                                            │
webapp/routes/pages.py ◄────────────────────────────────────────────────────
    │  GET /assessments/{id}  → renders assessment_detail.html
    │  GET /assessments/{id}/report.docx  → streams Word report
    │  GET /assessments/{id}/report.pdf   → streams PDF report
    ▼
User (Browser) — receives completed report
```

---

## 7. Important Business Entities

| Entity | Table | Description |
|--------|-------|-------------|
| `Assessment` | `assessments` | Central record: vendor, status, progress, summary, report_data |
| `AssessmentFile` | `assessment_files` | Raw uploaded file bytes (questionnaires, artifacts, policies, clauses) |
| `Embedding` | `embeddings` | pgvector embeddings (1536-dim) for RAG retrieval |
| `PipelineOutput` | `pipeline_outputs` | Full JSON output of each pipeline step |
| `DefaultDocument` | `default_documents` | Admin-uploaded default policies and contract clauses |
| `AppUser` | `app_users` | Application users with bcrypt passwords and roles |
| `LoginAuditLog` | `login_audit_logs` | Every login attempt with IP, user agent, success/failure |
| `AppSession` | `app_sessions` | Persistent browser sessions (absolute 8h + 60min idle timeout) |
| `LlmCache` | `llm_cache` | DB-tier LLM response cache keyed by SHA-256(prompt) |
| `EmbeddingCache` | `embedding_cache` | DB-tier embedding cache keyed by SHA-256(text) |

---

## 8. Deployment Architecture

### Development
```
docker compose up -d          # starts PostgreSQL + Redis
python -m webapp.main         # runs app at http://127.0.0.1:8085
```

### Production
```
docker compose -f docker-compose.prod.yml up -d
# Starts:
#   tprm-db  — PostgreSQL 16 + pgvector (localhost:5432 only)
#   tprm-app — TPRM app (0.0.0.0:8085, behind reverse proxy)
```

### Dockerfile
- Python base image
- Copies all source files
- Runs `uvicorn webapp.main:app --host 0.0.0.0 --port 8085`

---

## 9. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | (auto-generated) | Session signing key |
| `POSTGRES_USER` | `tprm_user` | DB username |
| `POSTGRES_PASSWORD` | `tprm_password` | DB password |
| `POSTGRES_DB` | `tprm_db` | DB name |
| `POSTGRES_HOST` | `127.0.0.1` | DB host |
| `POSTGRES_PORT` | `5432` | DB port |
| `OPENAI_API_KEY` | `` | OpenAI API key (or Titan Gateway key) |
| `OPENAI_MODEL` | `gpt-4` | LLM model name |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `TPRM_HOST` | `127.0.0.1` | Web server bind host |
| `TPRM_PORT` | `8085` | Web server port |
| `TPRM_DEBUG` | `false` | Debug mode (enables Swagger UI) |
| `CLIENT_ID` | `` | Azure AD app client ID |
| `CLIENT_SECRET` | `` | Azure AD app client secret |
| `TENANT_ID` | `` | Azure AD tenant ID |
| `REDIRECT_URI` | `http://localhost:8085/auth/callback` | SSO callback URL |
| `SSO_ENABLED` | `true` | Enable/disable Azure AD SSO |
| `LLM_JUDGE_ENABLED` | `true` | Enable LLM quality-review pass |
| `LLM_CACHE_ENABLED` | `false` | Enable version-level output caching |
| `ALLOWED_ORIGINS` | `http://127.0.0.1:8085` | CORS allowed origins |
| `REQUESTS_CA_BUNDLE` | `` | Custom CA bundle for corporate proxies |
| `TPRM_SSL_VERIFY` | `true` | Set `false` to disable SSL verification |

---

## 10. Logging and Audit Mechanisms

- **Application logging**: Python `logging` module, format `%(asctime)s | %(levelname)s | %(name)s | %(message)s`
- **Log namespaces**: `tprm.app`, `tprm.auth`, `tprm.pipeline_runner`, `tprm.gap_analysis`, `tprm.embedding_service`, `tprm.judge`, `tprm.storage`, etc.
- **Login audit**: Every login attempt (success/failure) written to `login_audit_logs` table with IP, user agent, timestamp
- **Session audit**: Sessions stored in `app_sessions` with absolute + idle timeout tracking
- **Pipeline audit**: Assessment `progress` JSON updated at each of 7 steps in real time
- **HITL audit**: Every human override stored in `hitl_feedback` with original + modified values and reviewer justification
- **LLM cache audit**: Cache hits/misses logged at INFO level with key prefix

---

## 11. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Dual FastAPI apps | `webapp/` for browser users; `app/` for programmatic/MCP clients |
| Sync DB for pipeline | Pipeline runs in a background thread; async sessions not needed, sync is simpler |
| pgvector over JSON store | Replaced file-based `json_vector_store.py` with native cosine similarity in PostgreSQL |
| Deterministic UUIDs | `uuid.uuid5()` ensures same gap/remediation ID across re-runs for deduplication |
| Two-tier LLM cache | Memory cache (speed) + DB cache (persistence across restarts) |
| Assessment fingerprinting | SHA-256 of all inputs → skip LLM if inputs unchanged (cost savings) |
| LLM Judge | Multi-pass quality review catches duplicates/severity mismatches post-generation |
| HITL feedback table | Human corrections tracked separately so they don't corrupt AI-generated data |
