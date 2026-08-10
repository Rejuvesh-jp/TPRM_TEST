# TPRM AI — Security Architecture

> **Purpose**: Security controls, authentication flows, and compliance mechanisms for MCP audit integration.

---

## Authentication Methods

### 1. Form-Based Login (Local Users)
**Route**: `POST /api/login`  
**Module**: `webapp/auth.py`

**Flow**:
1. User submits email + password
2. Email normalized to lowercase
3. Check account lockout (`_failed_logins` in-memory tracker)
4. Load user from `app_users` table (bcrypt hash)
5. `bcrypt.checkpw(password, stored_hash)` — constant-time comparison
6. On success: create session in `app_sessions` table, set `HttpOnly` cookie
7. Log to `login_audit_logs` table

**Security controls**:
- Passwords hashed with **bcrypt** (work factor 12)
- Account **lockout after 5 failed attempts for 15 minutes**
- In-memory lockout tracker resets on restart (intentional — prevents persistent DoS)
- All login events (success + failure) logged with IP and user agent

### 2. Azure AD SSO (Microsoft Identity Platform)
**Routes**: `GET /auth/login`, `GET /auth/callback`, `GET /auth/logout`  
**Module**: `webapp/routes/sso.py`, `webapp/gateway_token.py`  
**Library**: MSAL (Microsoft Authentication Library)

**Flow**:
1. User clicks "Login with Microsoft"
2. `GET /auth/login` → generate state token → redirect to Azure AD
3. Azure AD authenticates user → redirects to `/auth/callback?code=...&state=...`
4. Validate state against `sso_state` cookie using `hmac.compare_digest` (CSRF guard)
5. `msal.acquire_token_by_authorization_code()` → get ID token + access token
6. Extract email from claims (`upn` / `preferred_username` / `email`)
7. Create app session (same as local login)

**Configuration**:
- `CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID` from `.env`
- `REDIRECT_URI` auto-detected from request or configured in `.env`
- `SSO_ENABLED` flag (default: true)

**AI Gateway Token** (separate from SSO):
- OAuth 2.0 **Client Credentials** grant (`acquire_token_for_client()`)
- App-level token, not user-level
- Cached in-memory with 10-minute refresh buffer
- Thread-safe: `threading.Lock` with double-check locking pattern
- Scope: `api://46ecea3c-9158-403d-bbc1-151157e182ea/.default`

### 3. API Key Authentication (Core API)
**Module**: `app/core/security.py`  
**Header**: `X-API-Key`

```python
# Constant-time comparison — prevents timing attacks
if not hmac.compare_digest(x_api_key, configured_key):
    raise HTTPException(401, "Invalid API key")
```

**Key separation**: `API_KEY` (for HTTP authentication) is distinct from `SECRET_KEY` (for session signing).

---

## Session Management

**Module**: `webapp/auth.py`  
**Storage**: `app_sessions` PostgreSQL table (not in-memory, survives restarts)

| Property | Value |
|----------|-------|
| Session token | Cryptographically random UUID (`secrets.token_urlsafe`) |
| Cookie name | `session_token` |
| Cookie flags | `HttpOnly`, `SameSite=Lax`, `Secure` (when HTTPS) |
| Absolute timeout | **8 hours** from session creation |
| Idle timeout | **60 minutes** from last activity |
| CSRF token | Per-session random token stored in `app_sessions.csrf_token` |

---

## Password Security

**Module**: `webapp/auth.py`

```python
# Hash: bcrypt with work factor 12
bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))

# Verify: constant-time bcrypt check
bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
```

**Password complexity requirements** (`validate_password_complexity()`):
- Minimum 12 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one special character

**Legacy plaintext detection**: If stored hash doesn't start with `$2` (bcrypt prefix), logs a warning and falls back to `hmac.compare_digest` (time-safe) comparison.

---

## CSRF Protection

**Module**: `webapp/main.py` → CSRF middleware

```python
# Validates X-CSRF-Token header for state-changing requests on authenticated sessions
if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
    if request.url.path not in {"/login", "/api/login"}:
        session = get_session(request)
        if session:
            expected = session.get("csrf_token", "")
            received = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(received, expected):
                return JSONResponse({"detail": "CSRF token validation failed"}, 403)
```

---

## Authorization / Role-Based Access Control

**Roles**: `admin`, `analyst`

| Capability | Admin | Analyst |
|------------|-------|---------|
| View all assessments | ✓ | Only own |
| Create assessments | ✓ | ✓ |
| Delete assessments | ✓ | ✗ |
| Manage users | ✓ | ✗ |
| Upload default policies/clauses | ✓ | ✗ |
| Change pipeline settings | ✓ | ✗ |
| View analytics | ✓ | ✓ |
| Download reports | ✓ | ✓ (own only) |

**Ownership check** (`_check_assessment_access()`):
```python
if user.get("role") != "admin":
    owner = meta.get("created_by_email", "").lower()
    if owner and owner != user["email"].lower():
        raise HTTPException(403, "Access denied to this assessment")
```

**Core API role check** (`app/core/security.py`):
```python
def require_role(*roles: str):
    async def _check_role(user: dict = Depends(verify_api_key)):
        if user.get("role") not in roles:
            raise HTTPException(403, f"Role not allowed. Required: {roles}")
        return user
    return _check_role
```

---

## File Upload Security

**Module**: `webapp/routes/api.py` → `_validate_upload()`

| Check | Implementation |
|-------|---------------|
| Extension whitelist | Global: `.pdf .docx .txt .csv .xlsx .xls .pptx .json .zip .png .jpg .jpeg` |
| Per-category restriction | Questionnaires: `.pdf` only; Policies: `.pdf .docx .txt` |
| MIME type validation | `python-magic` reads magic bytes (not extension) |
| Double extension rejection | `"." in Path(filename).stem` → rejected (e.g. `file.exe.pdf`) |
| Max file size | 100 MB per file |
| Text format handling | `text/plain` allowed only for `.txt`, `.csv`, `.json` extensions |

---

## Security HTTP Headers

Applied by `webapp/main.py` middleware to **all responses**:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0                          (CSP preferred over legacy filter)
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'unsafe-inline' cdn.jsdelivr.net;
  style-src 'self' 'unsafe-inline' fonts.googleapis.com;
  font-src 'self' fonts.gstatic.com data:;
  img-src 'self' data: blob:;
  connect-src 'self';
  object-src 'none';
  base-uri 'self'
```

---

## Rate Limiting

**Library**: `slowapi`  
**Module**: `webapp/limiter.py`

Applied to:
- Login endpoint
- File upload endpoints

---

## CORS Configuration

```python
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", f"http://127.0.0.1:{PORT}").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)
```

Production: override `ALLOWED_ORIGINS` env var with actual domain(s).  
Core API (`app/main.py`): uses `allow_origins=["*"]` in DEBUG, `[]` in production.

---

## Data Security

| Concern | Mitigation |
|---------|-----------|
| NULL bytes in DB | `_strip_null_bytes()` sanitises all JSONB writes |
| SQL injection | SQLAlchemy parameterised queries (no raw string interpolation) |
| Secrets in code | All secrets via `.env` / environment variables |
| Default secrets | `validate_secrets()` logs `CRITICAL` if `SECRET_KEY` = default value |
| Timing attacks | `hmac.compare_digest()` for all secret comparisons |
| Open redirect | Redirect URIs hardcoded or validated |
| API key isolation | `API_KEY` ≠ `SECRET_KEY` (separate concerns) |
| XSS | Jinja2 auto-escaping + CSP header |
| CSRF | Per-session token validated on all state-changing requests |

---

## Audit Logging

### Login Audit (`login_audit_logs` table)
Every login attempt logged with:
- `user_email` — attempted address
- `action` — `LOGIN_SUCCESS` or `LOGIN_FAILED`
- `ip_address` — client IP (from `request.client.host`)
- `user_agent` — browser/client (truncated to 200 chars)
- `timestamp` — UTC ISO string

### Application Logging
- Format: `"%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"`
- Namespaces: `tprm.auth`, `tprm.app`, `tprm.pipeline_runner`, `tprm.gap_analysis`, etc.
- Level: INFO in production, DEBUG if `TPRM_DEBUG=true`
- Noisy libraries suppressed: `httpx`, `openai` → WARNING; `sqlalchemy.engine` → WARNING (INFO in debug)

### HITL Audit (`hitl_feedback` table)
Every human override to AI output stored with:
- `entity_type` + `entity_id` — what was changed
- `original_value` — AI-generated value (JSONB)
- `modified_value` — reviewer's correction (JSONB)
- `justification` — required text explanation
- `reviewer_id` — who made the change
- `timestamp` — when

---

## Sensitive Configuration Reference

| Secret | Where used | Risk if leaked |
|--------|-----------|----------------|
| `SECRET_KEY` | Session cookie signing | Session forgery |
| `POSTGRES_PASSWORD` | DB connection | Full DB access |
| `OPENAI_API_KEY` | LLM + embedding calls | API cost/data exposure |
| `CLIENT_SECRET` | Azure AD SSO + AI Gateway | App impersonation |
| `API_KEY` | Core API authentication | Unauthorised API access |
