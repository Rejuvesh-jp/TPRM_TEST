# Data Model: TPRM Assessment Platform

**Feature**: `001-tprm-assessment`
**Date**: 2026-03-09

## Entities & Relationships

### `vendors`
- **id**: UUID (PK)
- **name**: varchar(255)
- **domain**: varchar(255) (unique)
- **status**: enum('active', 'inactive', 'pending_onboarding')
- **created_at**: datetime
- **updated_at**: datetime

### `assessments`
- **id**: UUID (PK)
- **vendor_id**: UUID (FK -> vendors.id)
- **status**: enum('draft', 'processing', 'review_pending', 'completed')
- **started_at**: datetime
- **completed_at**: datetime
- **reviewer_id**: UUID (FK -> users.id, nullable)
- **version**: int

### `questionnaires`
- **id**: UUID (PK)
- **assessment_id**: UUID (FK -> assessments.id)
- **file_metadata**: JSON (s3 key, original filename, size, etc.)
- **parsed_content**: JSONB (raw extracted text/structure)
- **analysis_status**: enum('pending', 'analyzing', 'completed', 'failed')
- **created_at**: datetime

### `questions`
- **id**: UUID (PK)
- **questionnaire_id**: UUID (FK -> questionnaires.id)
- **section**: varchar(255)
- **control_id**: varchar(50)
- **question_text**: text
- **response_text**: text
- **justification**: text
- **risk_relevance**: enum('high', 'medium', 'low', 'none')
- **expected_evidence**: text
- **claim_strength**: float (0.0 - 1.0)
- **flags**: JSONB (e.g., weak response, ambiguous)

### `artifacts`
- **id**: UUID (PK)
- **assessment_id**: UUID (FK -> assessments.id)
- **file_metadata**: JSON (s3 key, filename, type, size)
- **processing_status**: enum('uploaded', 'extracted', 'chunked', 'embedded', 'analyzed', 'failed')
- **error_log**: text (nullable)
- **created_at**: datetime

### `artifact_chunks`
- **id**: UUID (PK)
- **artifact_id**: UUID (FK -> artifacts.id)
- **chunk_index**: int
- **content**: text
- **embedding**: vector(1536) (pgvector)
- **metadata**: JSONB (page number, section header, token count)

### `artifact_insights`
- **id**: UUID (PK)
- **artifact_id**: UUID (FK -> artifacts.id)
- **insight_type**: enum('policy_coverage', 'certification', 'control', 'compliance_gap')
- **description**: text
- **confidence**: float (0.0 - 1.0)
- **source_chunks**: JSONB (array of chunk_ids)

### `policies`
- **id**: UUID (PK)
- **title**: varchar(255)
- **version**: varchar(50)
- **content**: text
- **embedding**: vector(1536) (pgvector, specialized for policy search)
- **active**: boolean

### `contract_clauses`
- **id**: UUID (PK)
- **category**: varchar(100)
- **content**: text
- **embedding**: vector(1536) (pgvector)
- **standard_clause**: boolean (true if template, false if vendor-specific)

### `gap_assessments`
- **id**: UUID (PK)
- **assessment_id**: UUID (FK -> assessments.id)
- **question_id**: UUID (FK -> questions.id, nullable)
- **gap_type**: enum('missing_artifact', 'unsupported_claim', 'policy_violation', 'control_missing')
- **description**: text
- **severity**: enum('critical', 'high', 'medium', 'low')
- **source_refs**: JSONB (list of source artifact/question/policy IDs)

### `risk_assessments`
- **id**: UUID (PK)
- **assessment_id**: UUID (FK -> assessments.id)
- **gap_id**: UUID (FK -> gap_assessments.id)
- **risk_level**: enum('critical', 'high', 'medium', 'low')
- **rationale**: text
- **remediation_plan**: text
- **status**: enum('open', 'mitigated', 'accepted')

### `recommendations`
- **id**: UUID (PK)
- **risk_assessment_id**: UUID (FK -> risk_assessments.id)
- **clause_text**: text
- **justification**: text

### `hitl_feedback`
- **id**: UUID (PK)
- **entity_type**: varchar(50) (e.g., 'risk', 'gap', 'question_analysis')
- **entity_id**: UUID
- **reviewer_id**: UUID
- **original_value**: JSONB
- **modified_value**: JSONB
- **justification**: text
- **timestamp**: datetime

## Indexes

- `vectors_idx` on `artifact_chunks(embedding)` using `hnsw`
- `vectors_policy_idx` on `policies(embedding)` using `hnsw`
- `vectors_clause_idx` on `contract_clauses(embedding)` using `hnsw`
- Standard indexes on all FK columns for join performance.
