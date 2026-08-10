# TPRM AI — MCP Tool Definitions

> **Purpose**: Proposed MCP (Model Context Protocol) tool definitions for Claude Cowork integration.
> These tools expose the TPRM platform's capabilities to Claude as callable functions.

---

## Tool Design Philosophy

Each MCP tool maps to one or more TPRM API endpoints. Tools are designed to be:
- **Idempotent** where possible
- **Stateless** — context passed in parameters, not assumed from prior calls
- **Structured** — all outputs are typed JSON, not free text

**Base URL**: `http://localhost:8085` (configure per deployment)  
**Auth**: Session cookie (acquired via `tprm_login` tool first)

---

## Authentication Tools

### `tprm_login`
Authenticate to the TPRM platform and establish a session.

**Input**:
```json
{
  "email": "analyst@titan.com",
  "password": "..."
}
```

**Output**:
```json
{
  "success": true,
  "user": {
    "email": "analyst@titan.com",
    "name": "Reju",
    "role": "admin"
  },
  "session_token": "...",
  "csrf_token": "..."
}
```

**Maps to**: `POST /api/login`

---

### `tprm_sso_login`
Get the SSO login URL for Azure AD authentication.

**Output**:
```json
{
  "login_url": "https://login.microsoftonline.com/..."
}
```

**Maps to**: `GET /auth/login` (redirects to Azure AD)

---

## Assessment Management Tools

### `tprm_create_assessment`
Create a new vendor assessment with file uploads.

**Input**:
```json
{
  "vendor_name": "Acme Corp",
  "division": "Watches",
  "use_openai": true,
  "spoc_email": "vendor@acme.com",
  "files": {
    "questionnaires": ["path/to/sig_lite.pdf"],
    "artifacts": ["path/to/iso27001.pdf", "path/to/soc2.pdf"],
    "policies": ["path/to/infosec_policy.pdf"],
    "contract_clauses": ["path/to/clauses.docx"]
  }
}
```

**Output**:
```json
{
  "assessment_id": "uuid",
  "vendor_name": "Acme Corp",
  "vendor_id": "VND-A3F2B1",
  "version": 1,
  "status": "pending"
}
```

**Maps to**: `POST /api/assessments`

---

### `tprm_list_assessments`
List all assessments, optionally filtered.

**Input**:
```json
{
  "status": "completed",
  "division": "Watches",
  "vendor_name_contains": "acme"
}
```

**Output**:
```json
{
  "assessments": [
    {
      "id": "uuid",
      "vendor_name": "Acme Corp",
      "vendor_id": "VND-A3F2B1",
      "version": 2,
      "status": "completed",
      "division": "Watches",
      "nature_of_engagement": "high",
      "created_at": "2026-05-01T10:30:00+05:30",
      "summary": {
        "total_gaps": 12,
        "critical": 2,
        "high": 5,
        "medium": 4,
        "low": 1,
        "overall_risk_rating": "high"
      }
    }
  ],
  "total": 42
}
```

**Maps to**: `GET /api/assessments`

---

### `tprm_get_assessment`
Get full details of a specific assessment.

**Input**:
```json
{ "assessment_id": "uuid" }
```

**Output**:
```json
{
  "id": "uuid",
  "vendor_name": "Acme Corp",
  "status": "completed",
  "pre_assessment_scores": {
    "total_score": 45,
    "sensitivity": "high",
    "responses": [...]
  },
  "summary": {...},
  "report_data": {
    "executive_summary": "...",
    "gaps": [...],
    "risks": [...],
    "remedial_actions": [...],
    "recommendations": [...]
  }
}
```

**Maps to**: `GET /api/assessments/{id}`

---

### `tprm_get_assessment_status`
Poll the pipeline execution status of an assessment.

**Input**:
```json
{ "assessment_id": "uuid" }
```

**Output**:
```json
{
  "status": "running",
  "progress": {
    "current_step": 4,
    "total_steps": 7,
    "step_label": "Running gap analysis..."
  },
  "started_at": "2026-05-11T09:15:00+05:30"
}
```

**Maps to**: `GET /api/assessments/{id}` (subset of fields)

---

### `tprm_run_assessment`
Trigger the AI pipeline for an existing assessment.

**Input**:
```json
{ "assessment_id": "uuid" }
```

**Output**:
```json
{ "status": "running", "message": "Pipeline started" }
```

**Maps to**: `POST /api/assessments/{id}/run`

---

### `tprm_delete_assessment`
Delete an assessment and all associated data.

**Input**:
```json
{ "assessment_id": "uuid", "confirm": true }
```

**Output**:
```json
{ "deleted": true, "assessment_id": "uuid" }
```

**Maps to**: `DELETE /api/assessments/{id}`

---

## Vendor Tools

### `tprm_lookup_vendor`
Look up a vendor by ID to check existing assessments and next version.

**Input**:
```json
{ "vendor_id": "VND-A3F2B1" }
```

**Output**:
```json
{
  "vendor_id": "VND-A3F2B1",
  "vendor_name": "Acme Corp",
  "latest_version": 2,
  "next_version": 3,
  "division": "Watches"
}
```

**Maps to**: `GET /api/vendor-lookup?vendor_id=VND-A3F2B1`

---

## Pre-Assessment Tools

### `tprm_submit_pre_assessment`
Submit Pre-Business Assessment responses to calculate engagement sensitivity.

**Input**:
```json
{
  "assessment_id": "uuid",
  "responses": [
    { "q": 1, "answer": "yes" },
    { "q": 2, "answer": "no" },
    { "q": 3, "answer": "yes" },
    { "q": 4, "answer": "no" },
    { "q": 5, "answer": "yes" },
    { "q": 6, "answer": "no" },
    { "q": 7, "answer": "no" },
    { "q": 8, "answer": "no" },
    { "q": 9, "answer": "no" },
    { "q": 10, "answer": "yes" }
  ]
}
```

**Output**:
```json
{
  "total_score": 50,
  "sensitivity": "high",
  "responses": [
    { "q": 1, "text": "Is the third party solution a Cloud service?", "answer": "yes", "score": 5 }
  ]
}
```

**Maps to**: `POST /api/assessments/{id}/pre-assessment`

**Question reference**:
| Q# | Topic | Yes Score |
|----|-------|-----------|
| 1 | Cloud service (SaaS/PaaS/IaaS) | 5 |
| 2 | Physical/logical access to Titan infra | 5 |
| 3 | Connects from external network | 5 |
| 4 | Developing hardware/software for Titan | 5 |
| 5 | Access to PII (customer/employee data) | 20 |
| 6 | Processing financial data | 20 |
| 7 | Titan systems hosted on vendor premises | 5 |
| 8 | Had a security incident in past 12 months | 5 |
| 9 | Access to payment card data | 20 |
| 10 | Failure would trigger BCP/DRP | 20 |

---

## Report Tools

### `tprm_get_gaps`
Get the list of identified compliance gaps for an assessment.

**Input**:
```json
{
  "assessment_id": "uuid",
  "severity": "critical",
  "gap_type": "control_missing"
}
```

**Output**:
```json
{
  "gaps": [
    {
      "id": "uuid",
      "control_id": "H.1.1",
      "section": "H. Access Control",
      "gap_type": "control_missing",
      "severity": "critical",
      "confidence": 0.92,
      "description": "Multi-factor authentication is not enforced for privileged accounts.",
      "evidence_assessment": "Vendor confirmed MFA is optional; no artifact evidence of enforcement.",
      "source_refs": {
        "questionnaire": ["H.1.1"],
        "artifact": ["iso27001_cert.pdf"],
        "policy": ["infosec_policy.pdf"]
      }
    }
  ],
  "total": 12
}
```

**Maps to**: `GET /api/assessments/{id}` (report_data.gaps)

---

### `tprm_get_remediation_plan`
Get the remediation action plan for an assessment.

**Input**:
```json
{ "assessment_id": "uuid", "priority": "immediate" }
```

**Output**:
```json
{
  "remedial_actions": [
    {
      "id": "uuid",
      "gap_id": "uuid",
      "action": "Implement MFA for all privileged account access within 30 days.",
      "priority": "immediate",
      "timeline": "Within 30 days",
      "owner": "Vendor Security Team",
      "acceptance_criteria": "MFA enforced for all admin/privileged accounts; evidence via screenshot or config export."
    }
  ]
}
```

---

### `tprm_get_recommendations`
Get contract clause recommendations for an assessment.

**Input**:
```json
{ "assessment_id": "uuid" }
```

**Output**:
```json
{
  "recommendations": [
    {
      "gap_id": "uuid",
      "existing_clauses": ["Clause 4.2: Data Protection Requirements"],
      "new_clause_suggestions": ["Add clause requiring vendor to maintain MFA for all remote access."]
    }
  ]
}
```

---

### `tprm_download_report`
Download the assessment report.

**Input**:
```json
{
  "assessment_id": "uuid",
  "format": "docx"
}
```

**Output**:
```json
{
  "download_url": "/api/assessments/{id}/report.docx",
  "filename": "TPRM_Assessment_AcmeCorp_v2.docx"
}
```

**Maps to**: `GET /api/assessments/{id}/report.docx` or `report.pdf`

---

### `tprm_set_risk_rating`
Manually assign a risk rating to an assessment.

**Input**:
```json
{
  "assessment_id": "uuid",
  "risk_rating": "high"
}
```

**Output**:
```json
{ "updated": true, "risk_rating": "high" }
```

**Maps to**: `PATCH /api/assessments/{id}/risk-rating`

---

## Analytics Tools

### `tprm_get_analytics`
Get platform-wide analytics and dashboard metrics.

**Output**:
```json
{
  "total_assessments": 42,
  "completed": 30,
  "running": 2,
  "pending": 8,
  "failed": 2,
  "unique_vendors": 18,
  "gaps_by_severity": { "critical": 12, "high": 47, "medium": 93, "low": 31 },
  "top_vendors_by_gaps": [
    { "vendor": "Acme Corp", "gaps": 23, "month": "Mar '26" }
  ],
  "monthly_trend": [
    { "month": "May '26", "count": 5 }
  ]
}
```

---

## Admin Tools

### `tprm_list_users`
List all application users (admin only).

**Output**:
```json
{
  "users": [
    {
      "email": "analyst@titan.com",
      "name": "John Doe",
      "role": "analyst",
      "is_active": true
    }
  ]
}
```

---

### `tprm_create_user`
Create a new application user (admin only).

**Input**:
```json
{
  "email": "newuser@titan.com",
  "name": "Jane Smith",
  "role": "analyst",
  "password": "Str0ng!Pass"
}
```

---

### `tprm_get_settings`
Get current pipeline feature flags.

**Output**:
```json
{
  "llm_judge_enabled": true,
  "llm_cache_enabled": false
}
```

---

### `tprm_update_settings`
Update pipeline feature flags (admin only).

**Input**:
```json
{
  "llm_judge_enabled": false,
  "llm_cache_enabled": true
}
```

---

## HITL (Human-in-the-Loop) Tools

### `tprm_submit_feedback`
Submit reviewer correction to an AI-generated assessment element.

**Input**:
```json
{
  "entity_type": "gap",
  "entity_id": "uuid",
  "reviewer_id": "analyst@titan.com",
  "original_value": { "severity": "medium", "description": "..." },
  "modified_value": { "severity": "critical", "description": "Updated after reviewing vendor response..." },
  "justification": "Vendor confirmed the control was not in place despite their initial claim."
}
```

**Maps to**: `POST /api/v1/hitl`

---

## Suggested MCP Tool Registration (Claude Cowork)

```python
# MCP server tools registration example
tools = [
    Tool(name="tprm_list_assessments", ...),
    Tool(name="tprm_get_assessment", ...),
    Tool(name="tprm_get_gaps", ...),
    Tool(name="tprm_get_remediation_plan", ...),
    Tool(name="tprm_get_analytics", ...),
    Tool(name="tprm_submit_pre_assessment", ...),
    Tool(name="tprm_create_assessment", ...),
    Tool(name="tprm_get_assessment_status", ...),
    Tool(name="tprm_set_risk_rating", ...),
    Tool(name="tprm_submit_feedback", ...),
]
```

---

## Common Workflows for Claude

### "Assess a new vendor"
1. `tprm_lookup_vendor` — check if vendor exists
2. `tprm_create_assessment` — create with files
3. `tprm_submit_pre_assessment` — score sensitivity
4. Poll `tprm_get_assessment_status` until `completed`
5. `tprm_get_gaps` — review identified gaps
6. `tprm_get_remediation_plan` — review remediation actions
7. `tprm_download_report` — get Word/PDF report

### "Review high-risk vendors"
1. `tprm_list_assessments` with `status: "completed"`
2. Filter by `summary.overall_risk_rating == "high"`
3. For each: `tprm_get_gaps` filtered by `severity: "critical"`
4. `tprm_get_recommendations` to see contractual mitigations

### "Dashboard summary for management"
1. `tprm_get_analytics` — get all metrics
2. Format: total assessments, completed count, gap distribution, top risk vendors

### "Override AI gap severity"
1. `tprm_get_assessment` — get current gaps
2. Identify gap to correct
3. `tprm_submit_feedback` with original + modified severity + justification
