# TPRM AI — AI Knowledge Base

> **Purpose**: Master reference document for AI/LLM retrieval and semantic search. 
> Optimised for Claude Cowork MCP integration — covers all 25 knowledge domains.

---

## 1. What is TPRM AI?

TPRM AI is an enterprise **Third-Party Risk Management** platform built for **Titan Company Limited** (an Indian luxury goods company with brands in Watches, Jewellery, and Eyewear). It automates vendor security assessments using AI — replacing manual analyst effort with a multi-step LLM pipeline.

**Core value proposition**: Upload a vendor's SIG Lite questionnaire and supporting documents → get a complete risk assessment report with gaps, risk scores, remediation plans, and contract recommendations in minutes.

---

## 2. Core Business Purpose

### Problem it solves
Before a vendor can access Titan systems, data, or infrastructure, Titan's IT security team must assess the vendor's security posture. This historically required analysts to manually review hundreds of questionnaire responses, cross-reference certificates, read audit reports, and write findings — a process taking days per vendor.

### How TPRM AI solves it
1. **Automates questionnaire analysis**: Parses SIG Lite PDFs (21 sections, 300+ questions) automatically
2. **Evidence-based gap detection**: Uses RAG (Retrieval-Augmented Generation) to find contradictions between what vendors claim and what their documents prove
3. **Risk scoring**: LLM assigns risk levels (critical/high/medium/low) with rationale
4. **Remediation planning**: Generates actionable remediation actions with timelines and owners
5. **Contract recommendations**: Suggests contract clauses to mitigate identified risks
6. **Quality control**: Multi-pass LLM judge reviews and corrects the draft assessment

---

## 3. Technology Stack

### Languages and Frameworks
- **Python 3.11** — primary language
- **FastAPI 0.115.6** — web framework (two apps: webapp + core API)
- **SQLAlchemy 2.0** — ORM (async for API, sync for pipeline)
- **Pydantic 2.x** — data validation and settings management
- **Jinja2** — HTML templates

### AI / ML
- **OpenAI API** — LLM (`gpt-4` / `gpt-5.4-azure` via Titan AI Gateway) + embeddings (`text-embedding-3-small`, 1536 dims)
- **Titan AI Gateway** — corporate OpenAI proxy (OAuth 2.0 client credentials)
- **pgvector** — PostgreSQL extension for vector similarity search (cosine distance)
- **RAG** (Retrieval-Augmented Generation) — used for evidence retrieval

### Document Processing
- **PyMuPDF (fitz)** — fast PDF rendering and text extraction
- **PyPDF** — PDF text layer extraction
- **python-docx** — DOCX parsing and report generation
- **openpyxl** — XLSX processing
- **pytesseract / Windows OCR** — fallback OCR for scanned PDFs

### Infrastructure
- **PostgreSQL 16 + pgvector** — primary database with vector search
- **Redis 7** — available in docker-compose (optional, not actively used)
- **Docker + Docker Compose** — containerisation (dev + prod configs)
- **uvicorn** — ASGI server
- **bcrypt** — password hashing
- **MSAL** — Microsoft Authentication Library (Azure AD SSO)
- **slowapi** — rate limiting

---

## 4. Application Architecture

### Dual FastAPI Application Design
```
Port 8085 (webapp/)          |  Internal (app/)
─────────────────────────────|─────────────────────
Jinja2 HTML templates        |  Pure JSON REST API
Session cookie auth          |  X-API-Key auth
Azure AD SSO via MSAL        |  Role-based access
Browser users                |  Programmatic / MCP clients
Background pipeline thread   |  Async request handling
```

### Key Modules
| Module | Purpose |
|--------|---------|
| `webapp/main.py` | Web app entry point, middleware stack |
| `webapp/auth.py` | Session auth, bcrypt, lockout |
| `webapp/pipeline_runner.py` | 7-step assessment pipeline |
| `webapp/db_storage.py` | Assessment CRUD |
| `webapp/pg_vector_store.py` | pgvector embedding operations |
| `webapp/report_generator.py` | PDF + Word report generation |
| `webapp/gateway_token.py` | AI Gateway token (client credentials) |
| `services/gap_analysis_service.py` | Core RAG + LLM gap detection |
| `services/llm_judge.py` | Multi-pass quality review |
| `services/embedding_service.py` | Embedding with 2-tier cache |
| `services/llm_cache.py` | LLM response caching |
| `services/assessment_fingerprint.py` | Input deduplication |
| `app/core/security.py` | API key auth + role enforcement |

---

## 5. Frontend Architecture

### Technology
- **Jinja2** server-side rendering — no separate SPA framework
- **Bootstrap** (CDN) — responsive UI components
- **Chart.js** — dashboard charts
- **Google Fonts** — typography

### Page Structure (13 templates)
| Template | Route | Purpose |
|----------|-------|---------|
| `base.html` | — | Layout: navbar, sidebar, head tags |
| `home.html` | `/home` | Public landing page |
| `login.html` | `/login` | Login form |
| `dashboard.html` | `/` | Main dashboard with KPIs and charts |
| `assessments_list.html` | `/assessments` | Tabular list of all assessments |
| `new_assessment.html` | `/assessments/new` | Assessment creation form + file upload |
| `assessment_detail.html` | `/assessments/{id}` | Full assessment report view |
| `assessment_analytics.html` | `/assessment-analytics/{id}` | Per-assessment charts |
| `analytics_list.html` | `/analytics` | Platform-wide analytics |
| `settings.html` | `/settings` | Pipeline settings (admin) |
| `admin_defaults.html` | `/admin/defaults` | Default policy/clause management |
| `user_management.html` | `/user-management` | User CRUD (admin) |
| `api_test.html` | `/test-api` | API test UI (debug mode only) |

---

## 6. Backend Architecture

### Core Services Layer (`services/`)
| Service | Role in Pipeline |
|---------|----------------|
| `ocr_service.py` | Text extraction from any document format |
| `questionnaire_parser.py` | SIG Lite PDF → structured Q&A |
| `artifact_processor.py` | Chunk + embed vendor documents |
| `policy_processor.py` | Chunk + embed Titan policies |
| `clause_processor.py` | Chunk + embed contract clauses |
| `embedding_service.py` | OpenAI embeddings + cache |
| `gap_analysis_service.py` | RAG + LLM → identify gaps |
| `risk_assessment_service.py` | LLM → risk score per gap |
| `remedial_plan_service.py` | LLM → remediation action per gap |
| `recommendation_service.py` | RAG + LLM → contract clause recs |
| `llm_judge.py` | Multi-pass quality review |
| `llm_cache.py` | Memory + DB LLM response cache |
| `assessment_fingerprint.py` | SHA-256 input fingerprinting |

---

## 7. Database Architecture

### Primary Database: PostgreSQL 16 + pgvector

**Key tables (webapp schema)**:

| Table | Purpose |
|-------|---------|
| `assessments` | Central assessment record with all metadata and output |
| `assessment_files` | Uploaded file bytes (raw binary storage) |
| `embeddings` | pgvector 1536-dim embeddings for RAG |
| `pipeline_outputs` | Full JSON output per pipeline step |
| `default_documents` | Admin-uploaded policies/clauses shared across assessments |
| `app_users` | Users with bcrypt passwords |
| `app_sessions` | Persistent browser sessions |
| `login_audit_logs` | Immutable login audit trail |
| `llm_cache` | SHA-256 keyed LLM response cache |
| `embedding_cache` | SHA-256 keyed embedding cache |

**Vector search**: `embedding <=> query_vector` (cosine distance, pgvector)  
**Embedding dimensions**: 1536 (OpenAI text-embedding-3-small)

---

## 8. Authentication and Authorization

### Authentication methods
1. **Form login** — email + bcrypt password → session cookie
2. **Azure AD SSO** — OAuth 2.0 authorization code flow via MSAL
3. **API key** — `X-API-Key` header for core API

### Session Security
- Stored in `app_sessions` table (survives restarts)
- Absolute timeout: 8 hours
- Idle timeout: 60 minutes
- CSRF token per session, validated on all state-changing requests

### Roles
- `admin`: Full access — all assessments, user management, settings, default documents
- `analyst`: Own assessments only, no admin functions

### Account Lockout
- 5 failed login attempts → 15-minute lockout
- In-memory tracker (resets on restart, intentional)

---

## 9. API Structure

### Web API (Port 8085, `/api/`)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/assessments` | GET | List assessments |
| `/api/assessments` | POST | Create assessment + upload files |
| `/api/assessments/{id}` | GET | Get assessment detail |
| `/api/assessments/{id}/run` | POST | Trigger pipeline |
| `/api/assessments/{id}` | DELETE | Delete assessment |
| `/api/assessments/{id}/risk-rating` | PATCH | Set manual risk rating |
| `/api/assessments/{id}/pre-assessment` | POST | Submit PBA responses |
| `/api/assessments/{id}/report.docx` | GET | Download Word report |
| `/api/assessments/{id}/report.pdf` | GET | Download PDF report |
| `/api/vendor-lookup` | GET | Look up vendor by ID |
| `/api/analytics` | GET | Dashboard analytics data |
| `/api/settings` | GET/POST | Pipeline feature flags |
| `/api/login` | POST | Form login |
| `/api/users` | GET/POST | User management |
| `/health` | GET | Health check |

### Core API (`app/`, `/api/v1/`)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/questionnaires` | POST | Upload + parse questionnaire |
| `/api/v1/artifacts` | POST | Upload + process artifact |
| `/api/v1/assessments` | GET/POST | Assessment CRUD |
| `/api/v1/assessments/{id}` | GET | Get with all relations |
| `/api/v1/policies` | POST | Upload + embed policy |
| `/api/v1/hitl` | POST | Submit HITL feedback |

---

## 10. Key Services and Utilities

### Gap Analysis Service (`services/gap_analysis_service.py`)
The most critical service. Cross-references:
- Vendor questionnaire claims → artifact evidence (RAG, cosine similarity)
- Vendor posture → policy requirements (RAG)
- Vendor posture → contract obligations (RAG)
- Calls LLM with combined context → identifies gaps

Gap types: `control_missing`, `policy_violation`, `evidence_gap`, `process_gap`, `future_risk`  
Gap severity: `critical`, `high`, `medium`, `low`

### Embedding Service (`services/embedding_service.py`)
- Wraps OpenAI `text-embedding-3-small`
- 2-tier cache: in-memory + `embedding_cache` DB table
- Mock mode: SHA-256 seeded PRNG for deterministic 1536-dim vectors
- Batch lookup: one SQL query for all missing cache keys

### LLM Judge (`services/llm_judge.py`)
- 3-pass iterative quality review of draft assessment
- Each pass: reviews gaps → returns corrections → corrections applied → next pass
- Catches: duplicates, unsupported gaps, severity misalignments, vague wording
- Does NOT regenerate from scratch — only flags and corrects issues

### LLM Cache (`services/llm_cache.py`)
- Key: SHA-256(system_prompt + user_prompt)
- Memory tier (fast) + DB tier (persistent)
- Guarantees same prompt → same response (determinism)

### Assessment Fingerprint (`services/assessment_fingerprint.py`)
- SHA-256 of: all file bytes + chunk IDs + prompt versions + model name + judge flag
- If fingerprint matches a prior version → reuse that version's output (skip pipeline)
- Prompt version constants must be manually incremented on prompt edits

---

## 11. Workflow Orchestration

### 7-Step Assessment Pipeline (Background Thread)
```
Step 1: Pre-Business Assessment scoring (sensitivity: low/medium/high)
Step 2: Questionnaire parsing (SIG Lite → Q&A pairs + embeddings)
Step 3: Artifact processing (chunk + embed vendor documents)
Step 4: Load default policies and contract clauses
Step 5: Gap analysis (RAG + LLM)
  5a. Risk scoring per gap
  5b. Remedial plan generation per gap
  5c. Contract clause recommendations
Step 6: LLM Judge (optional multi-pass quality review)
Step 7: Save output to DB, update status → completed
```

### Execution model
- **Background thread** (`threading.Thread`, daemon=True)
- Progress tracked in `assessments.progress` JSONB (real-time)
- Status transitions: `pending → running → completed / failed`

---

## 12. Reporting and Analytics

### Report formats
- **Word (.docx)**: Full formatted report via python-docx
  - Cover page, executive summary, PBA table, gap analysis, risk table, remedial plan, recommendations
  - Indigo/navy colour scheme, Calibri font, Titan logo
- **PDF (.pdf)**: Same content via ReportLab

### Dashboard analytics
- KPI cards: total/completed/running/pending/failed assessments
- Chart: gap severity distribution (donut)
- Chart: status breakdown (doughnut)
- Chart: top 8 vendors by gap count (horizontal bar)
- Chart: assessments per month — last 12 months (line)
- Filters: division, status, vendor name search

---

## 13. Dashboard Logic

- All chart data computed server-side in `webapp/routes/pages.py`
- Dashboard shows **all assessments** (not per-user)
- Charts rendered client-side with **Chart.js** from JSON data injected into templates
- Monthly trend: rolling 12-month window computed at request time

---

## 14. Background Jobs

No Celery or external task queue. Pipeline runs in `threading.Thread` (daemon).  
`app/workers/tasks.py` contains sync functions designed to be queue-friendly.

---

## 15. External Integrations

| Integration | Protocol | Purpose |
|-------------|----------|---------|
| OpenAI / Titan AI Gateway | HTTPS REST | LLM completions + embeddings |
| Microsoft Azure AD | OAuth 2.0 / OIDC | SSO + user authentication |
| PostgreSQL | TCP (psycopg2) | Primary database |
| Redis | TCP | Optional (in docker-compose, not actively used) |

**AI Gateway**: Corporate OpenAI proxy at Titan. Uses client credentials OAuth2.  
Token scope: `api://46ecea3c-9158-403d-bbc1-151157e182ea/.default`  
Token cached in-memory with 10-minute pre-expiry refresh.

---

## 16. Configuration Management

### Settings priority (highest wins)
1. Value saved via Admin UI → `config/pipeline_settings.json`
2. Environment variable (`LLM_JUDGE_ENABLED`, `LLM_CACHE_ENABLED`)
3. Hardcoded default

### Feature flags
| Flag | Default | Effect |
|------|---------|--------|
| `LLM_JUDGE_ENABLED` | `true` | Run multi-pass quality review after draft |
| `LLM_CACHE_ENABLED` | `false` | Reuse cached output for identical inputs |

### Configuration files
| File | Purpose |
|------|---------|
| `.env` | All secrets and environment config |
| `config/pipeline_settings.json` | Runtime feature flags (mutable via UI) |
| `config/users.json` | Seed users for initial setup |
| `config/login_activity.json` | Seed login audit data |
| `alembic.ini` | Alembic migration config |

---

## 17. Security

### Controls implemented
- bcrypt password hashing (work factor 12)
- Session absolute (8h) and idle (60min) timeouts
- Account lockout (5 attempts → 15 min)
- CSRF tokens on all state-changing requests
- MIME type validation by magic bytes (not extension)
- Double extension rejection
- Constant-time secret comparisons (`hmac.compare_digest`)
- Full security header suite (CSP, HSTS, X-Frame-Options, etc.)
- Separate `API_KEY` and `SECRET_KEY` (no key dual use)
- Role-based access (admin vs analyst)
- Ownership checks (analysts only see own assessments)

### Compliance mitigations
- CWE-256 (plaintext passwords) → bcrypt
- CWE-613 (session expiry) → dual timeout
- CWE-307 (brute force) → account lockout

---

## 18. File Upload/Download Mechanisms

### Upload
1. Browser form submits `multipart/form-data` to `POST /api/assessments`
2. Server reads raw bytes, validates MIME + extension via `python-magic`
3. Bytes stored directly in `assessment_files.file_data` (LargeBinary)
4. Files written to temp dir during pipeline execution, cleaned up after

### Download
- `GET /api/assessments/{id}/report.docx` → `StreamingResponse` with `python-docx` buffer
- `GET /api/assessments/{id}/report.pdf` → `StreamingResponse` with ReportLab buffer
- `GET /api/assessments/{id}/files/{filename}` → serves uploaded file bytes

---

## 19. Risk and Compliance Modules

### Pre-Business Assessment (PBA)
10 yes/no questions → engagement sensitivity score  
Scores: low (≤10), medium (≤20), high (>20)  
High-weight questions: PII access (20), financial data (20), payment card (20), BCP/DRP impact (20)

### SIG Lite Questionnaire (Standard Information Gathering)
Industry-standard security assessment questionnaire  
21 sections covering: Enterprise Risk, Info Assurance, Asset Management, HR Security, Physical Security, IT Operations, Access Control, App Security, Incident Management, Resilience, Compliance, Endpoint Security, Network Security, ESG, Privacy, Threat Management, Server Security, Cloud Hosting

### Gap Types
| Type | Meaning |
|------|---------|
| `control_missing` | Required security control not implemented |
| `policy_violation` | Vendor practice violates Titan policy |
| `evidence_gap` | Vendor claims control but no document evidence |
| `process_gap` | Process exists but not consistently followed |
| `future_risk` | Emerging risk not yet a gap but warrants monitoring |

### Risk Levels
`critical` → `high` → `medium` → `low`

---

## 20. Deployment Architecture

### Development
```
docker compose up -d  →  PostgreSQL + Redis
python -m webapp.main  →  App at http://127.0.0.1:8085
```

### Production (`docker-compose.prod.yml`)
```
tprm-db   → PostgreSQL 16 + pgvector (localhost:5432 only)
tprm-app  → TPRM app (0.0.0.0:8085, behind reverse proxy)
```

### Key deployment notes
- DB port bound to `127.0.0.1` only (not externally accessible)
- App serves on `0.0.0.0:8085` (reverse proxy expected)
- Swagger UI disabled in production (`TPRM_DEBUG != true`)
- Health check: `GET /health` → `{"status": "healthy"}`

---

## 21. Environment Variables

Critical variables for deployment:
```
SECRET_KEY          — session signing key (must be random, long)
POSTGRES_PASSWORD   — DB password
OPENAI_API_KEY      — OpenAI or Titan Gateway API key
CLIENT_ID           — Azure AD app client ID
CLIENT_SECRET       — Azure AD app client secret
TENANT_ID           — Azure AD tenant ID
OPENAI_MODEL        — LLM model (default: gpt-4)
TPRM_PORT           — Web server port (default: 8085)
TPRM_DEBUG          — Enable debug mode (default: false)
ALLOWED_ORIGINS     — CORS origins (default: localhost)
```

---

## 22. Logging and Audit

### Application logs
- Format: `HH:MM:SS | LEVEL | namespace | message`
- Namespaces: `tprm.app`, `tprm.auth`, `tprm.pipeline_runner`, `tprm.gap_analysis`, etc.

### Persistent audit trails
| Audit type | Table | Content |
|-----------|-------|---------|
| Login attempts | `login_audit_logs` | email, action, IP, user-agent, timestamp |
| Sessions | `app_sessions` | creation, last active, expiry |
| HITL overrides | `hitl_feedback` | original + modified values, justification, reviewer |
| Pipeline steps | `pipeline_outputs` | full JSON per step |

---

## 23. Important Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.115.6 | Web framework |
| uvicorn | 0.34.0 | ASGI server |
| sqlalchemy | ≥2.0 | ORM |
| psycopg2-binary | ≥2.9 | PostgreSQL driver (sync) |
| pgvector | ≥0.3 | PostgreSQL vector extension |
| openai | 1.58.1 | LLM + embeddings |
| bcrypt | ≥4.0 | Password hashing |
| msal | ≥1.28 | Azure AD authentication |
| python-docx | 1.1.2 | Word report generation |
| reportlab | ≥4.0 | PDF report generation |
| PyMuPDF | 1.27.2 | PDF parsing + OCR rendering |
| slowapi | ≥0.1.9 | Rate limiting |
| pydantic-settings | 2.7.1 | Settings from env vars |
| tiktoken | 0.8.0 | Token counting for prompts |
| tenacity | 9.0.0 | LLM retry logic |

---

## 24. Data Flow Between Modules

```
File Upload → db_storage.save_uploaded_file() → assessment_files table
     ↓
pipeline_runner.run_pipeline_async()
     ↓
ocr_service.extract_text() → raw text
     ↓
questionnaire_parser.parse_sig_lite_pdf() → questions[]
embedding_service.embed() → question embeddings
     ↓
artifact_processor → chunks[] + embeddings[]
pg_vector_store.save() → embeddings table
     ↓
policy_processor + clause_processor → policy/clause chunks[]
     ↓
gap_analysis_service.run_gap_analysis()
  embedding_service.similarity_search() → evidence chunks (RAG)
  llm_fn(gap_analysis_prompt) → gaps[]
     ↓
risk_assessment_service.run_risk_assessment()
  llm_fn(risk_assessment_prompt) → risks[]
     ↓
remedial_plan_service.run_remedial_plan()
  llm_fn(remedial_plan_prompt) → remedial_actions[]
     ↓
recommendation_service.run_recommendations()
  embedding_service.similarity_search() → relevant clauses (RAG)
  llm_fn(recommendation_prompt) → recommendations[]
     ↓
llm_judge.run_llm_judge_multi_pass() → corrected assessment
     ↓
db_storage.save_report_data() → assessments.report_data (JSONB)
db_storage.update_status() → status = "completed"
     ↓
report_generator.generate_word() / generate_pdf()
  → StreamingResponse to browser
```

---

## 25. Important Business Entities

| Entity | Key attributes |
|--------|---------------|
| **Assessment** | vendor_name, vendor_id, version, division, status, sensitivity, risk_rating, summary, report_data |
| **Vendor** | vendor_id (VND-XXXXXX), vendor_name, division — no separate table; derived from assessments |
| **Gap** | control_id, section, gap_type, severity, confidence, description, source_refs |
| **Risk** | gap_id, risk_level, rationale, remediation_plan, regulatory_impact |
| **Remedial Action** | gap_id, action, priority, timeline, owner, acceptance_criteria |
| **Recommendation** | gap_id, existing_clauses, new_clause_suggestions |
| **Question** | control_id, section, question_text, response_text, justification, claim_strength |
| **Artifact** | filename, category, chunks, insights |
| **Policy** | title, version, content, embedding |
| **Contract Clause** | category, content, embedding, standard_clause |
| **User** | email, name, role (admin/analyst), password_hash |
| **Session** | user_email, csrf_token, created_at, last_active, expires_at |
| **HITL Feedback** | entity_type, entity_id, original_value, modified_value, justification, reviewer_id |

---

## Titan Company Context

- **Industry**: Luxury goods (Watches, Jewellery, Eyewear)
- **Headquarters**: India
- **Timezone displayed**: IST (UTC+5:30)
- **Regulatory context**: Processes PII, financial data, payment card data
- **Risk framework**: SIG Lite (Shared Assessments Standard Information Gathering)
- **AI infrastructure**: Titan AI Gateway (corporate OpenAI proxy with OAuth 2.0)
- **Identity provider**: Microsoft Azure AD (tenant: `5f274a9c-716a-48fd-8863-c407ea43c26d`)
