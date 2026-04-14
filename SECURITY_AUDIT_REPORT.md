# TPRM AI Assessment Platform — Security Audit Report

**Generated:** 2026-04-06  
**Scope:** Full application codebase security review  
**Standard:** OWASP Top 10 (2021), CWE/SANS Top 25, General Security Best Practices

---

## Executive Summary

The TPRM AI Assessment Platform was analyzed across **15 security check categories**. The audit identified **23 findings** — **8 Critical**, **7 High**, **5 Medium**, and **3 Low** severity issues. The most urgent concerns are **plaintext password storage**, **missing CSRF protection**, **overly permissive CORS**, and **hardcoded default secrets**.

---

## Security Checks Performed

| # | Security Check Category | OWASP Ref | Status |
|---|------------------------|-----------|--------|
| 1 | Authentication & Password Security | A07:2021 | ❌ CRITICAL |
| 2 | Session Management | A07:2021 | ⚠️ HIGH |
| 3 | Authorization & Access Control | A01:2021 | ⚠️ HIGH |
| 4 | Cross-Site Request Forgery (CSRF) | A01:2021 | ❌ CRITICAL |
| 5 | Cross-Site Scripting (XSS) | A03:2021 | ⚠️ MEDIUM |
| 6 | SQL Injection | A03:2021 | ✅ LOW RISK |
| 7 | Secrets & Configuration Management | A02:2021 | ❌ CRITICAL |
| 8 | CORS Policy | A05:2021 | ❌ CRITICAL |
| 9 | Security Headers | A05:2021 | ❌ CRITICAL |
| 10 | Rate Limiting & Brute Force Protection | A07:2021 | ❌ CRITICAL |
| 11 | File Upload Security | A04:2021 | ⚠️ MEDIUM |
| 12 | Dependency Vulnerability | A06:2021 | ⚠️ MEDIUM |
| 13 | Logging & Monitoring | A09:2021 | ⚠️ MEDIUM |
| 14 | Transport Security (HTTPS/TLS) | A02:2021 | ❌ CRITICAL |
| 15 | API Security & Input Validation | A08:2021 | ⚠️ HIGH |

---

## Detailed Findings

---

### 1. Authentication & Password Security (A07:2021 — Identification & Authentication Failures)

#### Finding 1.1 — CRITICAL: Passwords Stored in Plaintext
- **File:** `config/users.json`
- **Evidence:** Passwords are stored as raw strings (`"password": "Ram123@"`, `"password": "Rejuvesh@2025"`).
- **Impact:** Any attacker gaining file system read access obtains all user credentials instantly.
- **CWE:** CWE-256 (Plaintext Storage of a Password)
- **Recommendation:** Use `bcrypt` or `argon2` for password hashing. Replace the `password` field with `password_hash` and verify via `bcrypt.checkpw()` at login time.

#### Finding 1.2 — CRITICAL: No Password Hashing in Auth Module
- **File:** `webapp/auth.py` (line: `validate_credentials()`)
- **Evidence:** `user["password"] == password` — direct string comparison.
- **Impact:** Confirms plaintext storage; no salting or hashing is applied.
- **Note:** `setup_admin.py` has SHA-256 hashing code, but the main auth module does NOT use it. The `USER_MANAGEMENT_GUIDE.md` claims "SHA-256 with salt-based hashing" but this is **not implemented** in production code.

#### Finding 1.3 — HIGH: No Password Complexity Enforcement
- **File:** `webapp/auth.py`, `webapp/routes/user_management.py`
- **Evidence:** `add_user()` accepts any non-empty password string. No minimum length, complexity, or dictionary checks.
- **Recommendation:** Enforce minimum 12 characters, mixed case, numbers, and special characters. Consider using `zxcvbn` for strength estimation.

#### Finding 1.4 — MEDIUM: No Account Lockout After Failed Logins
- **File:** `webapp/auth.py`
- **Evidence:** Failed login attempts are logged but never counted or acted upon. Unlimited attempts are allowed.
- **CWE:** CWE-307 (Improper Restriction of Excessive Authentication Attempts)
- **Recommendation:** Lock accounts after 5 consecutive failed attempts for 15-30 minutes. Track failed attempts per email and IP.

---

### 2. Session Management (A07:2021)

#### Finding 2.1 — HIGH: In-Memory Session Store (No Persistence)
- **File:** `webapp/auth.py`
- **Evidence:** `_sessions: dict[str, dict] = {}` — sessions live in process memory.
- **Impact:** Server restart logs out all users. No session invalidation on scaling. Not suitable for multi-worker deployments.
- **Recommendation:** Use Redis or database-backed sessions with configurable TTL.

#### Finding 2.2 — HIGH: No Session Expiry/Timeout
- **File:** `webapp/auth.py`
- **Evidence:** Sessions are created via `secrets.token_urlsafe(32)` but never expire. They persist until the server restarts.
- **CWE:** CWE-613 (Insufficient Session Expiration)
- **Recommendation:** Add absolute timeout (e.g, 8 hours) and idle timeout (e.g., 30 minutes). Store creation timestamp and last-activity with each session.

#### Finding 2.3 — MEDIUM: Session Cookie Missing `Secure` Flag
- **File:** `webapp/routes/pages.py` (line 86)
- **Evidence:** `response.set_cookie("session_token", token, httponly=True, samesite="lax")` — no `secure=True`.
- **Impact:** Cookie can be transmitted over unencrypted HTTP, enabling session hijacking via network sniffing.
- **Recommendation:** Add `secure=True` when running behind HTTPS (which should be always in production).

---

### 3. Authorization & Access Control (A01:2021 — Broken Access Control)

#### Finding 3.1 — HIGH: No IDOR Protection on Assessment Endpoints
- **File:** `webapp/routes/api.py`
- **Evidence:** Endpoints like `/api/assessments/{assessment_id}/results` check authentication but NOT authorization. Any authenticated user can access/modify/delete any other user's assessments.
- **CWE:** CWE-639 (Authorization Bypass Through User-Controlled Key)
- **Recommendation:** Associate assessments with the user who created them. Verify ownership before allowing read/modify/delete. Admins may have override access.

#### Finding 3.2 — HIGH: API Key Equals Secret Key
- **File:** `app/core/security.py`
- **Evidence:** `if x_api_key == settings.SECRET_KEY: return {"user_id": "dev-user", "role": "admin"}` — the application's own secret key is accepted as a valid API key with admin privileges.
- **Impact:** Weak secret (default: `change-me-in-production`) grants full admin access.
- **Recommendation:** Use a proper API key management system. Never use the app secret as an auth token.

---

### 4. Cross-Site Request Forgery — CSRF (A01:2021)

#### Finding 4.1 — CRITICAL: No CSRF Protection
- **Files:** All POST/PUT/DELETE API routes
- **Evidence:** No CSRF tokens are generated or validated. The `grep` for `csrf` across the entire codebase returns zero results.
- **Impact:** An attacker can craft a malicious webpage that triggers state-changing operations (create/delete assessments, add/remove users) when visited by an authenticated user.
- **CWE:** CWE-352 (Cross-Site Request Forgery)
- **Recommendation:** Implement CSRF tokens for all state-changing endpoints. Use `starlette-csrf` middleware or add a custom `X-CSRF-Token` header validated against session-bound tokens.

---

### 5. Cross-Site Scripting — XSS (A03:2021 — Injection)

#### Finding 5.1 — MEDIUM: Email HTML Body Built via String Interpolation
- **File:** `webapp/routes/api.py` (send-gaps-email endpoint)
- **Evidence:** User-controlled data (`vendor_name`, `division`, `description`, `evidence_assessment`, `gap_type`) is interpolated directly into an HTML email body via f-strings without HTML encoding.
- **CWE:** CWE-79 (Cross-Site Scripting)
- **Impact:** If any gap description contains `<script>` tags or HTML, it will be rendered in the recipient's email client.
- **Recommendation:** Use `html.escape()` on all user-supplied values before including them in HTML.

#### Finding 5.2 — LOW: Jinja2 Auto-Escaping (Mitigated)
- **Observation:** Jinja2 templates auto-escape by default, which mitigates reflected/stored XSS in web pages. However, any use of `|safe` filter or `Markup()` should be audited.

---

### 6. SQL Injection (A03:2021 — Injection)

#### Finding 6.1 — LOW RISK: Mostly Parameterized
- **Observation:** The application uses SQLAlchemy ORM for most queries, which provides parameterized query protection. Raw SQL in `webapp/db.py` (`init_db()`) uses DDL statements with no user input, which is safe.
- **Note:** The `hashlib.md5(vendor_norm.encode()).hexdigest()` used in `db_storage.py` for vendor ID is deterministic and not injectable.
- **Status:** ✅ Acceptable. Continue using ORM-based queries.

---

### 7. Secrets & Configuration Management (A02:2021 — Cryptographic Failures)

#### Finding 7.1 — CRITICAL: Hardcoded Default Credentials
- **File:** `app/core/config.py`
- **Evidence:**
  ```python
  SECRET_KEY: str = "change-me-in-production"
  POSTGRES_USER: str = "tprm_user"
  POSTGRES_PASSWORD: str = "tprm_password"
  OPENAI_API_KEY: str = "your_openai_api_key_here"
  ```
- **Impact:** If `.env` file is not present or incomplete, the application runs with known default credentials.
- **CWE:** CWE-798 (Use of Hard-Coded Credentials)
- **Recommendation:** Remove all default credential values. Fail startup if required secrets are not provided via environment variables.

#### Finding 7.2 — HIGH: `.env` File in Workspace
- **File:** `.env`
- **Evidence:** The `.env` file exists in the project root. If not listed in `.gitignore`, it will be committed to version control with all secrets.
- **Recommendation:** Verify `.env` is in `.gitignore`. Use a secrets manager (Azure Key Vault, HashiCorp Vault) for production.

#### Finding 7.3 — HIGH: Microsoft Graph API Secrets in Environment
- **File:** `webapp/routes/api.py` (send-gaps-email endpoint)
- **Evidence:** `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` read from environment. These are OAuth client credentials with mail-sending permission.
- **Recommendation:** Use a secrets manager. Rotate client secrets regularly. Apply least-privilege scopes.

---

### 8. CORS Policy (A05:2021 — Security Misconfiguration)

#### Finding 8.1 — CRITICAL: Wildcard CORS Allows All Origins
- **File:** `webapp/main.py`
- **Evidence:**
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```
- **Impact:** Any website on the internet can make authenticated cross-origin requests to the API. Combined with the lack of CSRF protection, this enables full API access from any malicious page.
- **CWE:** CWE-942 (Overly Permissive Cross-domain Whitelist)
- **Recommendation:** Restrict `allow_origins` to the specific domains that need access (e.g., `["https://tprm.titan.co.in"]`). Remove `allow_headers=["*"]`.

---

### 9. Security Headers (A05:2021 — Security Misconfiguration)

#### Finding 9.1 — CRITICAL: No Security Response Headers
- **Files:** `webapp/main.py`, all route files
- **Evidence:** Zero security headers are set. Missing headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Content-Security-Policy`
  - `Strict-Transport-Security` (HSTS)
  - `X-XSS-Protection: 0` (to disable legacy filter, defer to CSP)
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy`
- **CWE:** CWE-693 (Protection Mechanism Failure)
- **Recommendation:** Add a middleware or `/app` startup hook that sets all security headers on every response:
  ```python
  @app.middleware("http")
  async def add_security_headers(request, call_next):
      response = await call_next(request)
      response.headers["X-Content-Type-Options"] = "nosniff"
      response.headers["X-Frame-Options"] = "DENY"
      response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
      response.headers["Content-Security-Policy"] = "default-src 'self'"
      response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
      return response
  ```

---

### 10. Rate Limiting & Brute Force Protection (A07:2021)

#### Finding 10.1 — CRITICAL: No Rate Limiting on Any Endpoint
- **Files:** All route files
- **Evidence:** No rate limiting middleware or decorators exist. The login endpoint allows unlimited attempts per second.
- **Impact:** Enables credential stuffing, brute force attacks, and denial of service.
- **CWE:** CWE-770 (Allocation of Resources Without Limits)
- **Recommendation:** Use `slowapi` (built on `limits`) for FastAPI rate limiting:
  - Login: 5 requests/minute per IP
  - API endpoints: 60 requests/minute per session
  - File upload: 10 requests/minute per session

---

### 11. File Upload Security (A04:2021 — Insecure Design)

#### Finding 11.1 — MEDIUM: File Size Read Into Memory Before Validation
- **File:** `webapp/routes/api.py`
- **Evidence:** `content = await f.read()` reads the entire file into memory, then checks `len(content) > MAX_UPLOAD_SIZE`. An attacker can send very large files to exhaust memory.
- **Recommendation:** Use streaming read with early termination, or set `max_request_size` at the web server level (nginx/uvicorn `--limit-max-body-size`).

#### Finding 11.2 — LOW: Magic Byte Validation Is Present (Good)
- **Observation:** File uploads validate MIME type via `python-magic` (`magic.from_buffer()`), check extensions, and reject double extensions. This is a solid defense-in-depth measure.
- **Status:** ✅ Well implemented.

#### Finding 11.3 — MEDIUM: No Antivirus/Malware Scanning
- **Observation:** Uploaded files (PDFs, DOCX, XLSX) are stored in the database and later processed by extraction libraries. No malware scanning is performed.
- **Recommendation:** Integrate ClamAV or an equivalent scanner before storing uploaded files.

---

### 12. Dependency Vulnerabilities (A06:2021 — Vulnerable & Outdated Components)

#### Finding 12.1 — MEDIUM: Dependency Versions May Have Known CVEs
- **File:** `requirements.txt`
- **Key Dependencies to Audit:**
  - `jinja2==3.1.4` — Check for template injection CVEs
  - `PyMuPDF==1.27.2` — PDF parsing library, historically has had CVEs
  - `openai==1.58.1` — Verify latest security patches
  - `psycopg2-binary>=2.9.0` — Binary wheel; use `psycopg2` (source) in production for security auditability
- **Recommendation:** Run `pip-audit` or `safety check` regularly. Pin all dependencies with hashes. Set up Dependabot/Snyk for continuous monitoring.

#### Finding 12.2 — LOW: Using MD5 for Vendor ID Generation
- **File:** `webapp/db_storage.py`
- **Evidence:** `hashlib.md5(vendor_norm.encode()).hexdigest()[:6]` — MD5 is used for non-cryptographic ID generation.
- **Impact:** Low — this is used for deterministic naming, not security. However, collision probability in 6 hex chars (16^6 = 16M) is non-trivial.
- **Recommendation:** Acceptable for current use, but document the collision risk. Consider SHA-256 truncated if paranoid.

---

### 13. Logging & Monitoring (A09:2021 — Security Logging & Monitoring Failures)

#### Finding 13.1 — MEDIUM: Login Activity Stored in JSON File
- **File:** `webapp/auth.py`, `config/login_activity.json`
- **Evidence:** Login audit log stored as a JSON file on disk, capped at 1000 entries. No centralized logging, no alerting on suspicious patterns.
- **Impact:** Log tampering is trivial with file system access. Log rotation deletes evidence.
- **Recommendation:** Send security events to a centralized SIEM/log system. Add alerts for: 5+ failed logins for same email, logins from new IPs, admin actions.

#### Finding 13.2 — LOW: No Request/Response Audit Logging
- **Observation:** API calls are not logged with details (who accessed what, when, from where). Only login events are tracked.
- **Recommendation:** Add access logging middleware that records user, endpoint, method, status code, and timestamp.

---

### 14. Transport Security — HTTPS/TLS (A02:2021)

#### Finding 14.1 — CRITICAL: No HTTPS Enforcement
- **File:** `webapp/main.py`, `webapp/config.py`
- **Evidence:** Application binds to `127.0.0.1:8085` via plain HTTP. No TLS certificate configuration. No HTTPS redirect middleware.
- **Impact:** All traffic including session tokens, passwords, and API keys transmitted in plaintext.
- **Recommendation:** Deploy behind a reverse proxy (nginx, Caddy, or Azure App Gateway) terminating TLS. Add `HTTPSRedirectMiddleware` from Starlette. Set `Strict-Transport-Security` header.

---

### 15. API Security & Input Validation (A08:2021 — Software & Data Integrity Failures)

#### Finding 15.1 — HIGH: Session Token Returned in API Login Response Body
- **File:** `webapp/routes/api.py` (`/api/login`)
- **Evidence:** `"session_token": token` is returned in the JSON response body.
- **Impact:** If the API is called from a browser, the token is accessible to JavaScript, defeating `httponly` cookie protection.
- **Recommendation:** Set the session cookie server-side only. Do not include the token in the response body.

#### Finding 15.2 — MEDIUM: Email Parameter Not Sanitized in URL Path
- **File:** `webapp/routes/user_management.py`
- **Evidence:** `@router.put("/api/users/{email}")` and `@router.delete("/api/users/{email}")` use raw email as URL path parameter.
- **Impact:** Special characters in email addresses could cause URL parsing issues.
- **Recommendation:** URL-encode the email or use request body/query parameter instead of path parameter.

#### Finding 15.3 — HIGH: `docs_url="/docs"` Exposes Swagger UI in Production
- **File:** `webapp/main.py`
- **Evidence:** `FastAPI(... docs_url="/docs" ...)` — Swagger UI and OpenAPI schema are publicly available.
- **Impact:** Exposes full API surface, request/response schemas, and parameter names to attackers.
- **Recommendation:** Disable in production: `docs_url=None, redoc_url=None, openapi_url=None` or protect behind auth middleware.

---

## Summary of Findings by Severity

| Severity | Count | Key Issues |
|----------|-------|-----------|
| 🔴 CRITICAL | 8 | Plaintext passwords, no CSRF, wildcard CORS, no security headers, hardcoded secrets, no rate limiting, no HTTPS, no password hashing |
| 🟠 HIGH | 7 | No session expiry, IDOR on assessments, API key = secret key, .env exposure, session token in response body, Swagger UI exposed, no password complexity |
| 🟡 MEDIUM | 5 | No account lockout, cookie missing `secure` flag, file size memory DoS, no malware scanning, login logs in JSON file |
| 🟢 LOW | 3 | Jinja2 auto-escape OK, magic validation OK, MD5 for non-crypto use |

---

## Priority Remediation Roadmap

### Immediate (Week 1) — Critical Fixes
1. **Hash all passwords** with `bcrypt` — replace plaintext in `users.json` and `auth.py`
2. **Restrict CORS** to specific origins
3. **Add CSRF protection** middleware
4. **Add security response headers** middleware
5. **Remove hardcoded default credentials** — fail on missing secrets
6. **Add rate limiting** on login and API endpoints

### Short-Term (Week 2-3) — High Fixes
7. **Implement session expiry** (absolute + idle timeouts)
8. **Add authorization checks** (user → assessment ownership)
9. **Remove session token from login response body**
10. **Disable Swagger UI** in production
11. **Deploy behind HTTPS** reverse proxy
12. **Enforce password complexity** rules

### Medium-Term (Month 2) — Hardening
13. **Centralize audit logging** (SIEM integration)
14. **Run dependency vulnerability scanning** (pip-audit, Dependabot)
15. **Add streaming file upload validation**
16. **Implement malware scanning** for uploads
17. **HTML-escape email template variables**

---

## Appendix: Files Analyzed

| File | Security Relevance |
|------|-------------------|
| `webapp/auth.py` | Authentication, session management, user storage |
| `webapp/routes/api.py` | All REST API endpoints, file uploads, email sending |
| `webapp/routes/pages.py` | HTML page routes, login/logout, cookie handling |
| `webapp/routes/user_management.py` | User CRUD, admin authorization |
| `webapp/main.py` | App initialization, CORS, middleware, static files |
| `webapp/config.py` | App configuration |
| `webapp/db.py` | Database connection, raw SQL in init |
| `webapp/db_storage.py` | Data access layer |
| `webapp/models.py` | ORM models |
| `webapp/pipeline_runner.py` | Background pipeline execution |
| `app/core/config.py` | Settings with defaults |
| `app/core/security.py` | API key auth, RBAC |
| `app/core/database.py` | Async DB connections |
| `config/users.json` | User credential storage |
| `docker-compose.yml` | Container orchestration |
| `requirements.txt` | Python dependencies |
| `.env` | Environment secrets |

---

*Report generated by automated security analysis. Manual penetration testing is recommended to validate findings.*
