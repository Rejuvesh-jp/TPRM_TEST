# TPRM AI — Assessment Pipeline Workflows

> **Purpose**: Detailed workflow documentation for MCP tool orchestration.

---

## Overview

The TPRM pipeline is a **7-step sequential processing workflow** that runs in a background thread for each assessment. It transforms raw uploaded documents into a structured risk assessment report.

**Entry point**: `webapp/pipeline_runner.py` → `run_pipeline_async(assessment_id)`  
**Execution model**: `threading.Thread` (sync, blocking — not async/await)  
**Progress tracking**: `assessments.progress` JSONB column updated at each step

---

## Step-by-Step Pipeline

### Step 0: Initialisation
- Load assessment metadata from DB
- Load all uploaded files from `assessment_files` table
- Check LLM cache: if assessment fingerprint matches a previous version, reuse that version's output (skip Steps 1–6)
- Update status to `running`

---

### Step 1: Pre-Business Assessment Scoring
**Service**: `pipeline_runner._score_pre_assessment()`  
**Input**: Pre-Business Assessment PDF(s)  
**Output**: `{responses: [...], total_score: N, sensitivity: "high"|"medium"|"low"}`

**Logic**:
1. Extract text from PBA documents via `ocr_service`
2. Parse all Q&A pairs using `questionnaire_parser.parse_generic_questionnaire()`
3. Match parsed questions to 10 canonical PBA questions using **keyword matching with greedy exclusive assignment** (strongest match wins, each question used only once)
4. Score: Q1–Q4,Q7,Q8 = 5 pts each; Q5,Q6,Q9,Q10 = 20 pts each
5. Sensitivity: ≤10 → low; ≤20 → medium; >20 → high
6. Save to `assessments.pre_assessment_scores`

---

### Step 2: Questionnaire Parsing
**Service**: `services/questionnaire_parser.py`  
**Input**: SIG Lite questionnaire PDF  
**Output**: Structured list of question dicts with embeddings

**SIG Lite sections parsed** (21 sections):
- BI (Business Information), DRL (Document Request List)
- A: Enterprise Risk Management
- B: Nth Party Management
- C: Information Assurance
- D: Asset and Info Management
- E: Human Resources Security
- F: Physical and Environmental Security
- G: IT Operations Management
- H: Access Control
- I: Application Security
- J: Cybersecurity Incident Management
- K: Operational Resilience
- L: Compliance Management
- M: Endpoint Security
- N: Network Security
- O: Environmental, Social and Governance
- P: Privacy Management
- T: Threat Management
- U: Server Security
- V: Cloud Hosting Services

**Key fields extracted per question**:
```json
{
  "id": "uuid5-deterministic",
  "control_id": "H.1.1",
  "section": "H. Access Control",
  "question_text": "...",
  "response_text": "Yes / No / N/A",
  "justification": "...",
  "risk_relevance": "high",
  "expected_evidence": "...",
  "claim_strength": 0.85,
  "flags": {...},
  "question_embedding": [1536 floats]
}
```

**Excluded from security analysis** (`INFO_ONLY_SECTIONS`):
- "Business Information"
- "Document Request List"
- "Section 0"
- "Section 22"

---

### Step 3: Artifact Processing
**Service**: `services/artifact_processor.py`  
**Input**: Vendor evidence documents (PDFs, DOCX, etc.)  
**Output**: Chunked + embedded documents stored in pgvector

**Processing per document**:
1. Extract text via `ocr_service.extract_text()` (with OCR fallback for scanned PDFs)
2. Split into overlapping chunks (default: 1000 chars / 200 overlap)
3. Generate 1536-dim embeddings via `embedding_service`
4. Store chunks in `embeddings` table (store_name = `artifacts`) via `PgVectorStore`

**OCR pipeline**:
- **Windows**: Windows OCR API via subprocess
- **Linux/Mac**: Tesseract (`pytesseract`)
- **Fallback resolution**: 200 DPI via PyMuPDF

---

### Step 4: Load Default Policies and Clauses
**Services**: `services/policy_processor.py`, `services/clause_processor.py`  
**Input**: Documents from `default_documents` table (uploaded by admin)  
**Output**: Chunked + embedded policy and clause data

---

### Step 5: Gap Analysis (Core Intelligence Step)
**Service**: `services/gap_analysis_service.py`  
**Input**: Questions, artifact chunks, policy chunks, clause chunks  
**Output**: List of gap dicts

**Sub-steps**:

#### 5a. RAG — Questions vs Artifact Evidence
```
For each security-domain question:
  query = "{section}: {question_text} | Response: {response_text[:200]}"
  query_embedding = embed(query)
  results = cosine_similarity_search(query_embedding, artifact_chunks, top_k=5)
```
- Deduplicates evidence chunks across all questions
- Stable sort by distance then chunk_id (determinism)
- Caps at 200 unique evidence chunks

#### 5b. RAG — Policy Context
```
query_embedding = embed("security compliance controls")
policy_results = cosine_similarity_search(query_embedding, policy_chunks, top_k=10)
```

#### 5c. RAG — Clause Context
```
clause_results = cosine_similarity_search(query_embedding, clause_chunks, top_k=10)
```

#### 5d. LLM — Gap Identification
Prompt: `app/prompts/gap_analysis.yaml`  
Input to LLM:
- Full questionnaire Q&A
- Top artifact evidence chunks
- Policy context
- Contract clause context

Output from LLM:
```json
{
  "gaps": [
    {
      "gap_type": "control_missing | policy_violation | evidence_gap | process_gap | future_risk",
      "control_id": "H.1.1",
      "severity": "critical | high | medium | low",
      "confidence": 0.85,
      "description": "...",
      "evidence_assessment": "...",
      "source_refs": { "questionnaire": [...], "artifact": [...], "policy": [...] }
    }
  ]
}
```

---

### Step 5b: Risk Scoring
**Service**: `services/risk_assessment_service.py`  
**Input**: Gap list  
**Output**: Risk scores per gap + overall_risk_rating + executive_summary

Prompt: `app/prompts/risk_assessment.yaml`  
LLM output per gap:
```json
{
  "gap_id": "...",
  "risk_level": "critical | high | medium | low",
  "rationale": "...",
  "remediation_plan": "...",
  "regulatory_impact": "...",
  "priority": "immediate | short_term | medium_term | long_term"
}
```

---

### Step 5c: Remedial Plan Generation
**Service**: `services/remedial_plan_service.py`  
**Input**: Eligible gaps (type: `control_missing`, `policy_violation`)  
**Output**: One remediation action per gap

**Timeline mapping**:
| Severity | Priority | Timeline |
|----------|----------|---------|
| Critical | Immediate | Within 30 days |
| High | Short-term | Within 90 days |
| Medium | Medium-term | Within 6 months |
| Low | Long-term | Within 12 months |

LLM output per gap:
```json
{
  "gap_id": "...",
  "action": "...",
  "priority": "immediate",
  "timeline": "Within 30 days",
  "owner": "Vendor Security Team",
  "acceptance_criteria": "..."
}
```

---

### Step 5d: Contract Clause Recommendations
**Service**: `services/recommendation_service.py`  
**Input**: Gaps, contract clause chunks  
**Output**: List of clause recommendations

**Logic**:
1. RAG: for each gap, find top-5 matching contract clauses by cosine similarity
2. RAG: additional searches for future-risk topics (AI governance, supply chain, data sovereignty, etc.)
3. Deduplicate matched clauses
4. LLM: identify applicable existing clauses + suggest new clauses per gap

Prompt: `app/prompts/recommendation.yaml`

---

### Step 6: LLM Judge (Quality Review)
**Service**: `services/llm_judge.py`  
**Enabled by**: `LLM_JUDGE_ENABLED` feature flag (default: true)  
**Input**: Full draft assessment (gaps, risks, remediation, recommendations)  
**Output**: Corrected/refined assessment

**Multi-pass review** (up to 3 iterations):
Each pass reviews and corrects:
- Duplicate gaps (same root cause, different wording)
- Unsupported gaps (no questionnaire/artifact backing)
- Missing controls (evidence present but gap not flagged)
- Severity misalignments
- Irrelevant clause recommendations
- Vague recommendation wording
- Executive summary contradictions

Each pass returns correction JSON that is **immediately applied** before the next pass. Process converges when corrections are minimal.

Prompt: `app/prompts/llm_judge.yaml`

---

### Step 7: Save and Finalise
1. Compute assessment summary: `{total_gaps, critical, high, medium, low, overall_risk_rating}`
2. Save full report data to `assessments.report_data` (JSONB)
3. Save pipeline step outputs to `pipeline_outputs` table
4. Update assessment `status` → `completed`
5. Update `completed_at` timestamp

---

## Pipeline State Machine

```
         ┌─────────┐
         │ pending │  (assessment created, files uploaded)
         └────┬────┘
              │  pipeline triggered
         ┌────▼────┐
         │ running │  (background thread active)
         └────┬────┘
         ┌────┴────┐
         │         │
    ┌────▼────┐  ┌─▼──────┐
    │completed│  │ failed │
    └─────────┘  └────────┘
```

**Progress JSON** (updated at each step):
```json
{
  "current_step": 4,
  "total_steps": 7,
  "step_label": "Running gap analysis..."
}
```

---

## Caching Layers

### 1. LLM Response Cache (`services/llm_cache.py`)
- **Key**: SHA-256(system_prompt + user_prompt)
- **Tier 1**: In-memory dict (fast, per-process)
- **Tier 2**: `llm_cache` PostgreSQL table (persistent across restarts)
- **When hit**: LLM API call is skipped; cached JSON returned

### 2. Embedding Cache (`services/embedding_service.py`)
- **Key**: SHA-256(text)
- **Tier 1**: In-memory dict
- **Tier 2**: `embedding_cache` PostgreSQL table
- **Batch lookup**: `_get_cached_embeddings_batch()` fetches all in one SQL query
- **When hit**: OpenAI Embeddings API call is skipped

### 3. Assessment Fingerprint / Version Cache (`services/assessment_fingerprint.py`)
- **Key**: SHA-256 of all input file bytes + retrieved chunk IDs + prompt versions + model name + judge flag
- Stored in `pipeline_outputs` for each assessment
- **When hit**: Entire pipeline is skipped; previous version's report reused
- **Enabled by**: `LLM_CACHE_ENABLED` feature flag (default: false)

### 4. OCR Text Cache (`services/ocr_service.py`)
- **Key**: SHA-256 of file bytes
- In-memory only (process lifetime)
- Prevents re-running OCR on the same file in a single session

---

## Background Job Pattern

The webapp uses **Python `threading.Thread`** (not Celery) for background pipeline execution:

```python
# In webapp/routes/api.py
thread = threading.Thread(
    target=run_pipeline_async,
    args=(assessment_id,),
    daemon=True,
)
thread.start()
```

The `app/` API uses sync task functions in `app/workers/tasks.py`:
- `parse_questionnaire_task(questionnaire_id)`
- `process_artifact_task(artifact_id)`
- `run_gap_analysis_task(assessment_id)`
- `run_risk_assessment_task(assessment_id)`

These are designed to be called by any task queue (Celery, etc.) as they are plain synchronous functions.

---

## LLM Prompt Templates

All prompts are YAML files in `app/prompts/`:

| File | Purpose |
|------|---------|
| `gap_analysis.yaml` | Gap identification from questionnaire + evidence |
| `risk_assessment.yaml` | Risk scoring per gap |
| `recommendation.yaml` | Contract clause recommendations |
| `remedial_plan.yaml` | Remediation action generation (implied by service) |
| `artifact_insight.yaml` | Artifact evidence extraction |
| `questionnaire_analysis.yaml` | Questionnaire Q&A analysis |
| `questionnaire_parsing.yaml` | Questionnaire structure parsing |
| `llm_judge.yaml` | Multi-pass quality review |

**YAML structure**:
```yaml
system: |
  You are a TPRM expert analyst...
user: |
  Vendor: {{vendor_name}}
  Questionnaire: {{questionnaire_data}}
  Evidence: {{artifact_evidence}}
  ...
```

---

## Determinism Design

The pipeline is engineered for **reproducible outputs** on identical inputs:

| Component | Determinism mechanism |
|-----------|-----------------------|
| Gap IDs | `uuid.uuid5(namespace, content_key)` |
| Risk IDs | `uuid.uuid5(namespace, f"risk:{gap_id}")` |
| Remediation IDs | `uuid.uuid5(namespace, f"remedial:{gap_id}:{action[:200]}")` |
| Embedding vectors | SHA-256 cache ensures same text → same vector |
| Evidence order | Stable sort by `(distance, chunk_id)` |
| Chunk IDs | SHA-256 of `(filename, chunk_index, content)` |
| LLM responses | SHA-256 cache ensures same prompt → same response |
| Version detection | Full-input fingerprint → version reuse |
