# TPRM AI — Database Architecture

> **Purpose**: Complete database schema, table relationships, and access patterns for MCP integration.

---

## Overview

The platform uses **PostgreSQL 16** with the **pgvector** extension.
Two ORM layers exist:

| Layer | Module | Session type | Used by |
|-------|--------|-------------|---------|
| `webapp/models.py` | webapp models | Sync (psycopg2) | Web app, pipeline runner |
| `app/models/models.py` | app models | Async (asyncpg) | Core API |

The webapp models are the **primary operational schema**. The app models represent an older design and are kept for the core API.

---

## Primary Schema (`webapp/models.py`)

### `assessments`
Central record for every vendor assessment.

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(36) PK | UUID |
| `vendor_name` | VARCHAR(500) | Vendor display name |
| `vendor_id` | VARCHAR(20) | Deterministic ID: `VND-` + MD5[:6].upper() of lowercase name |
| `version` | INTEGER | Assessment version per vendor (1, 2, 3...) |
| `division` | VARCHAR(200) | Titan business division |
| `nature_of_engagement` | VARCHAR(20) | `high` / `medium` / `low` (from PBA) |
| `pre_assessment_scores` | JSONB | `{responses: [...], total_score: N, sensitivity: "high"}` |
| `spoc_email` | VARCHAR(200) | Single point of contact email |
| `created_by_email` | VARCHAR(200) | User who created the assessment |
| `risk_rating` | VARCHAR(20) | Manually assigned: `high` / `medium` / `low` |
| `status` | VARCHAR(50) | `pending` / `running` / `completed` / `failed` |
| `use_openai` | BOOLEAN | Whether real OpenAI API is used (vs mock) |
| `created_at` | VARCHAR(50) | ISO timestamp (stored as string, shown in IST) |
| `started_at` | VARCHAR(50) | Pipeline start timestamp |
| `completed_at` | VARCHAR(50) | Pipeline completion timestamp |
| `error` | TEXT | Error message if pipeline failed |
| `progress` | JSONB | `{current_step: N, total_steps: 7, step_label: "..."}` |
| `summary` | JSONB | `{total_gaps: N, critical: N, high: N, medium: N, low: N, overall_risk: "..."}` |
| `report_data` | JSONB | Full report payload (gaps, risks, remediation, recommendations) |

**Indexes**: `vendor_id`, `created_by_email`, `status`

---

### `assessment_files`
Raw uploaded file bytes stored in the database.

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(36) PK | UUID |
| `assessment_id` | VARCHAR(36) FK → assessments | Parent assessment |
| `category` | VARCHAR(100) | `questionnaires` / `pre_business_assessment` / `artifacts` / `policies` / `contract_clauses` |
| `filename` | VARCHAR(500) | Original filename |
| `file_data` | LARGEBINARY | Raw file bytes |

**Cascade**: Deletes when parent assessment is deleted.

---

### `embeddings`
pgvector embedding store for RAG retrieval.

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(36) PK | UUID |
| `assessment_id` | VARCHAR(36) FK → assessments | Parent assessment |
| `store_name` | VARCHAR(100) | Logical store: `artifacts` / `policies` / `clauses` / `questions` |
| `chunk_id` | VARCHAR(100) | Deterministic chunk identifier |
| `source_document` | VARCHAR(500) | Source filename |
| `chunk_text` | TEXT | Text content of the chunk |
| `embedding` | Vector(1536) | pgvector 1536-dimensional embedding |

**Indexes**: `assessment_id + store_name` (composite), `embedding` (IVFFlat for ANN search)  
**Cosine similarity query**: `embedding <=> query_vector` (pgvector operator)

---

### `pipeline_outputs`
Full structured JSON output from each pipeline step.

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(36) PK | UUID |
| `assessment_id` | VARCHAR(36) FK → assessments | Parent assessment |
| `step_name` | VARCHAR(100) | Pipeline step identifier |
| `output_data` | JSONB | Complete step output |
| `created_at` | VARCHAR(50) | Timestamp |

---

### `default_documents`
Admin-uploaded default policies and contract clauses shared across all assessments.

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(36) PK | UUID |
| `doc_type` | VARCHAR(50) | `policy` / `clause` |
| `title` | VARCHAR(500) | Document title |
| `filename` | VARCHAR(500) | Original filename |
| `file_data` | LARGEBINARY | Raw bytes |
| `created_at` | VARCHAR(50) | Timestamp |

---

### `app_users`
Application users with bcrypt-hashed passwords.

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(36) PK | UUID |
| `email` | VARCHAR(200) UNIQUE | User email (lowercase) |
| `name` | VARCHAR(200) | Display name |
| `role` | VARCHAR(50) | `admin` / `analyst` |
| `password_hash` | VARCHAR(200) | bcrypt hash (work factor 12) |
| `is_active` | BOOLEAN | Soft delete flag |
| `created_at` | VARCHAR(50) | Timestamp |

---

### `app_sessions`
Persistent browser sessions (survive server restarts).

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(36) PK | Session token (UUID) |
| `user_email` | VARCHAR(200) | Owning user |
| `user_name` | VARCHAR(200) | Cached display name |
| `user_role` | VARCHAR(50) | Cached role |
| `csrf_token` | VARCHAR(64) | CSRF token for this session |
| `created_at` | VARCHAR(50) | Absolute session creation time |
| `last_active` | VARCHAR(50) | Last activity timestamp |
| `expires_at` | VARCHAR(50) | Absolute expiry (created_at + 8h) |

**Timeout logic**:
- Absolute: 8 hours from `created_at`
- Idle: 60 minutes since `last_active`

---

### `login_audit_logs`
Immutable audit trail of every login attempt.

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(36) PK | UUID |
| `timestamp` | VARCHAR(50) | ISO UTC timestamp |
| `user_email` | VARCHAR(200) | Attempted email |
| `name` | VARCHAR(200) | User display name |
| `action` | VARCHAR(50) | `LOGIN_SUCCESS` / `LOGIN_FAILED` |
| `ip_address` | VARCHAR(100) | Client IP |
| `user_agent` | VARCHAR(200) | Browser/client user agent (truncated to 200 chars) |

---

### `llm_cache`
Persistent LLM response cache (DB tier).

| Column | Type | Description |
|--------|------|-------------|
| `cache_key` | VARCHAR(64) PK | SHA-256(system_prompt + "\n---\n" + user_prompt) |
| `response` | TEXT | JSON-serialised LLM response |
| `created_at` | TIMESTAMP | Cache entry creation time |

---

### `embedding_cache`
Persistent embedding cache (DB tier).

| Column | Type | Description |
|--------|------|-------------|
| `cache_key` | VARCHAR(64) PK | SHA-256(text) |
| `embedding` | TEXT | JSON-serialised 1536-float array |

---

## Legacy Core API Schema (`app/models/models.py`)

Used by the `app/` FastAPI service. Separate from the webapp schema.

| Table | Key columns |
|-------|------------|
| `vendors` | `id` UUID, `name`, `domain` UNIQUE, `status` |
| `assessments` | `id` UUID, `vendor_id` FK, `status`, `started_at`, `completed_at`, `reviewer_id`, `version` |
| `questionnaires` | `id`, `assessment_id` FK, `file_name`, `parsed_content` JSONB, `analysis_status`, `analysis_result` JSONB |
| `questions` | `id`, `questionnaire_id` FK, `section`, `control_id`, `question_text`, `response_text`, `risk_relevance`, `claim_strength`, `flags` JSONB |
| `artifacts` | `id`, `assessment_id` FK, `file_name`, `file_type`, `processing_status` |
| `artifact_chunks` | `id`, `artifact_id` FK, `chunk_index`, `content`, `embedding` JSONB, `metadata_` JSONB |
| `artifact_insights` | `id`, `artifact_id` FK, `insight_type`, `description`, `confidence` |
| `policies` | `id`, `title`, `version`, `content`, `embedding` JSONB, `active` |
| `contract_clauses` | `id`, `category`, `content`, `embedding` JSONB, `standard_clause` |
| `gap_assessments` | `id`, `assessment_id` FK, `question_id` FK, `gap_type`, `description`, `severity`, `source_refs` JSONB |
| `risk_assessments` | `id`, `assessment_id` FK, `gap_id` FK, `risk_level`, `rationale`, `remediation_plan`, `status` |
| `recommendations` | `id`, `risk_assessment_id` FK, `clause_text`, `justification` |
| `hitl_feedback` | `id`, `entity_type`, `entity_id`, `reviewer_id`, `original_value` JSONB, `modified_value` JSONB, `justification` |

---

## Database Connection Configuration

### Webapp (Sync — psycopg2)
```python
DATABASE_URL = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=5, pool_recycle=1800)
```

### Core API (Async — asyncpg)
```python
DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
async_engine = create_async_engine(DATABASE_URL, pool_size=20, max_overflow=10, pool_pre_ping=True)
```

---

## Migrations

- Tool: **Alembic**
- Config: `alembic.ini`
- Migration scripts: `alembic/versions/`
- Initial migration: `da8a6ef64ab2_initial_schema.py` (creates all core app tables)
- Webapp tables created via: `Base.metadata.create_all(bind=engine)` in `init_db()` (idempotent)
- Schema evolution: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern (idempotent, no breaking changes)

---

## pgvector Usage

```sql
-- Enable extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Cosine distance search (lower = more similar)
SELECT *, embedding <=> '[0.1, 0.2, ...]'::vector AS distance
FROM embeddings
WHERE assessment_id = 'uuid' AND store_name = 'artifacts'
ORDER BY distance, chunk_id
LIMIT 5;
```

- Dimension: **1536** (matches OpenAI `text-embedding-3-small`)
- Distance metric: **cosine** (`<=>` operator)
- Similarity = `1 - cosine_distance`

---

## Data Integrity Patterns

| Pattern | Implementation |
|---------|---------------|
| Deterministic vendor ID | `VND-` + `MD5(lower(trim(vendor_name)))[:6].upper()` |
| Deterministic gap/risk IDs | `uuid.uuid5(namespace, content_key)` |
| NULL byte stripping | `_strip_null_bytes()` before all JSONB writes |
| Timezone normalisation | All timestamps stored as UTC ISO strings; displayed in IST (UTC+5:30) |
| Cascade deletes | `assessment_files`, `embeddings`, `pipeline_outputs` cascade on assessment delete |
