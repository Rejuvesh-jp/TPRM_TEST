# TPRM AI — API Reference

> **Purpose**: Complete API surface documentation for MCP tool binding and programmatic integration.

---

## Application A: `webapp/` Web API (Port 8085)

All endpoints below are served by `webapp/routes/api.py` under the `/api` prefix.
Authentication: **Session cookie** (`session_token`) — user must be logged in.

---

### Assessment Endpoints

#### `POST /api/assessments`
Create a new vendor assessment and upload supporting files.

**Auth**: Session required  
**Content-Type**: `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `vendor_name` | string | ✓ | Name of the vendor being assessed |
| `use_openai` | bool | — | Use real OpenAI API vs mock (default: false) |
| `division` | string | — | Titan business division requesting the assessment |
| `nature_of_engagement` | string | — | high / medium / low (auto-calculated from PBA if not set) |
| `spoc_email` | string | — | Single point of contact email |
| `questionnaires` | file[] | — | SIG Lite PDF questionnaire files |
| `pre_business_assessment` | file[] | — | Pre-Business Assessment PDFs |
| `artifacts` | file[] | — | Vendor evidence documents (certs, audit reports) |
| `policies` | file[] | — | Internal Titan policies |
| `contract_clauses` | file[] | — | Contract clause documents |

**Allowed file types per category**:
- `questionnaires`: `.pdf` only
- `pre_business_assessment`: `.pdf`, `.docx`, `.txt`
- `policies`: `.pdf`, `.docx`, `.txt`
- `contract_clauses`: `.docx`, `.pdf`, `.txt`
- `artifacts`: `.pdf`, `.docx`, `.txt`, `.csv`, `.xlsx`, `.xls`, `.pptx`, `.json`, `.zip`, `.png`, `.jpg`, `.jpeg`

**Max file size**: 100 MB per file  
**Security**: MIME type validated by `python-magic` (magic bytes, not extension alone). Double-extensions (e.g. `file.exe.pdf`) rejected.

**Response**:
```json
{
  "assessment_id": "uuid",
  "vendor_name": "Acme Corp",
  "status": "pending"
}
```

---

#### `GET /api/assessments`
List all assessments. Admins see all; analysts see only their own.

**Response**: Array of assessment metadata objects.

---

#### `GET /api/assessments/{assessment_id}`
Get a single assessment's metadata and pipeline output.

**Auth**: Session required + ownership check (analysts only see their own)

---

#### `POST /api/assessments/{assessment_id}/run`
Trigger the pipeline for an existing assessment.

---

#### `DELETE /api/assessments/{assessment_id}`
Delete an assessment and all associated files/embeddings.

---

#### `PATCH /api/assessments/{assessment_id}/risk-rating`
Manually assign a risk rating to an assessment.

**Body**:
```json
{ "risk_rating": "high" }
```

---

#### `POST /api/assessments/{assessment_id}/pre-assessment`
Submit Pre-Business Assessment (PBA) responses.

**Body**:
```json
{
  "responses": [
    { "q": 1, "answer": "yes" },
    { "q": 2, "answer": "no" }
  ]
}
```

**Returns**: `{ "responses": [...], "total_score": 45, "sensitivity": "high" }`

**Scoring logic**:
| Question | Topic | Yes Score |
|----------|-------|-----------|
| Q1 | Cloud service (SaaS/PaaS/IaaS) | 5 |
| Q2 | Physical/logical access to Titan infra | 5 |
| Q3 | Connects from external network | 5 |
| Q4 | Developing hardware/software for Titan | 5 |
| Q5 | Access to PII (customer/employee) | 20 |
| Q6 | Processing financial data | 20 |
| Q7 | Titan systems hosted on vendor premises | 5 |
| Q8 | Had a security incident in past 12 months | 5 |
| Q9 | Access to payment card data | 20 |
| Q10 | Failure would trigger BCP/DRP | 20 |

**Sensitivity thresholds**: ≤10 → low; ≤20 → medium; >20 → high

---

#### `GET /api/assessments/{assessment_id}/report.docx`
Download the generated Word report.

#### `GET /api/assessments/{assessment_id}/report.pdf`
Download the generated PDF report.

---

### Vendor Endpoints

#### `GET /api/vendor-lookup?vendor_id=VND-XXXXXX`
Look up a vendor by deterministic ID to auto-fill the assessment form.

**Response**:
```json
{
  "vendor_id": "VND-A3F2B1",
  "vendor_name": "Acme Corp",
  "latest_version": 2,
  "next_version": 3,
  "division": "Watches"
}
```

---

### Settings Endpoints (Admin only)

#### `GET /api/settings`
Get current pipeline feature flag settings.

#### `POST /api/settings`
Update pipeline feature flags.

**Body**:
```json
{
  "llm_judge_enabled": true,
  "llm_cache_enabled": false
}
```

---

### Analytics Endpoints

#### `GET /api/analytics`
Return aggregate analytics data for the dashboard.

**Response includes**:
- Total assessments, breakdown by status
- Gap count by severity (critical/high/medium/low)
- Top vendors by gap count
- Assessments created per month (last 12 months)
- Division-level breakdown

---

## Application B: `app/` Core API (Internal)

Base URL: `http://localhost:8000/api/v1`  
Auth: `X-API-Key` header (value from `API_KEY` environment variable)

---

### `POST /api/v1/questionnaires`
Upload and parse a questionnaire.

**Headers**: `X-API-Key: <key>`  
**Body**: `multipart/form-data` with `file` and `assessment_id`

---

### `POST /api/v1/artifacts`
Upload and process an artifact.

---

### `GET /api/v1/assessments`
List assessments (async DB query).

---

### `POST /api/v1/assessments`
Create a new assessment record.

---

### `GET /api/v1/assessments/{id}`
Get assessment with all related questionnaires, artifacts, gap assessments, and risk assessments.

---

### `POST /api/v1/policies`
Upload and embed a policy document.

---

### `POST /api/v1/hitl`
Submit human-in-the-loop feedback.

**Body**:
```json
{
  "entity_type": "gap_assessment",
  "entity_id": "uuid",
  "reviewer_id": "analyst@titan.com",
  "original_value": { ... },
  "modified_value": { ... },
  "justification": "Vendor provided updated certificate in follow-up email."
}
```

---

### `GET /health`
Health check endpoint (both apps).

**Response**: `{ "status": "healthy" }`

---

## Authentication Routes (`webapp/`)

### `GET /login`
Render login form.

### `POST /api/login`
Submit credentials (email + password).

**Body**: `application/x-www-form-urlencoded`
```
email=user@titan.com&password=secret
```

**Security**:
- bcrypt password verification
- Account lockout after 5 failed attempts for 15 minutes
- Login events logged to `login_audit_logs`
- Session token set as `HttpOnly` cookie

### `GET /auth/login`
Redirect to Microsoft Azure AD login (SSO flow).

### `GET /auth/callback`
Handle Azure AD callback — exchange code for token, create session.

**Security**: OAuth state parameter validated with `hmac.compare_digest` (CSRF guard).

### `GET /auth/logout` / `GET /logout`
Destroy session, clear cookie, redirect to `/login`.

---

## User Management Routes (Admin only)

### `GET /user-management`
Render user management page.

### `POST /api/users`
Create a new user.

**Body**:
```json
{
  "email": "analyst@titan.com",
  "name": "John Doe",
  "role": "analyst",
  "password": "Str0ng!Password"
}
```

**Password rules**: ≥12 chars, uppercase, lowercase, digit, special character.

### `PUT /api/users/{email}`
Update user (name, role, password).

### `DELETE /api/users/{email}`
Deactivate a user (soft delete).

---

## Page Routes

| Route | Template | Description |
|-------|----------|-------------|
| `GET /` | `dashboard.html` | Main dashboard with charts and assessment list |
| `GET /home` | `home.html` | Public landing page |
| `GET /assessments` | `assessments_list.html` | All assessments table |
| `GET /assessments/new` | `new_assessment.html` | Assessment creation form |
| `GET /assessments/{id}` | `assessment_detail.html` | Full assessment detail + report |
| `GET /analytics` | `analytics_list.html` | Analytics and reporting |
| `GET /assessment-analytics/{id}` | `assessment_analytics.html` | Per-assessment analytics |
| `GET /settings` | `settings.html` | Pipeline settings (admin) |
| `GET /user-management` | `user_management.html` | User admin (admin) |
| `GET /admin/defaults` | `admin_defaults.html` | Manage default policies/clauses |

---

## Security Headers Applied to All Responses

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; ...
```

## CSRF Protection

All `POST/PUT/PATCH/DELETE` requests on authenticated sessions require:
```
X-CSRF-Token: <token-from-session>
```
Token is stored in the session and validated using `hmac.compare_digest`.  
Login endpoints (`/login`, `/api/login`) are excluded (no session yet).

## Rate Limiting

Applied via `slowapi` on sensitive endpoints (login, file upload).
