"""
Web App Configuration
=====================
"""
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Directories
ASSESSMENTS_DIR = PROJECT_ROOT / "assessments"
ASSESSMENTS_DIR.mkdir(exist_ok=True)

# App settings
APP_NAME = "TPRM AI Assessment Platform"
APP_VERSION = "1.0.0"
HOST  = os.getenv("TPRM_HOST",  "127.0.0.1")
PORT  = int(os.getenv("TPRM_PORT", "8085"))
DEBUG = os.getenv("TPRM_DEBUG", "false").lower() == "true"

# SECRET_KEY — used for signing; auto-generated if not set in .env
import secrets as _secrets
SECRET_KEY = os.getenv("SECRET_KEY") or _secrets.token_hex(32)

# Azure AD SSO — credentials read from .env
SSO_ENABLED      = os.getenv("SSO_ENABLED", "true").lower() == "true"
SSO_CLIENT_ID    = os.getenv("CLIENT_ID", "").strip()
SSO_CLIENT_SECRET = os.getenv("CLIENT_SECRET", "").strip()
SSO_TENANT_ID    = os.getenv("TENANT_ID", "").strip()
SSO_REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8085/auth/callback")
SSO_AUTHORITY    = f"https://login.microsoftonline.com/{SSO_TENANT_ID}" if SSO_TENANT_ID else ""
SSO_SCOPES       = [
    "api://46ecea3c-9158-403d-bbc1-151157e182ea/access_as_user",  # Titan AI Gateway
]

# ── Assessment Pipeline Feature Flags ──────────────────────────────────────────
# These are initialized from env vars / saved settings file.
# They can be changed at runtime via the Admin UI without restarting the server.
# Use webapp.settings_store.save_settings() to update them programmatically.
#
# LLM_JUDGE_ENABLED: Run a second LLM review pass after the draft assessment.
#   ON  (default) → judge reviews draft, removes duplicates/unsupported gaps,
#                   improves wording, aligns severity.
#   OFF           → draft assessment is used as final output (backward compatible).
#
# LLM_CACHE_ENABLED: Cache final assessment output by input fingerprint.
#   ON  → if input files/answers are identical to a previous version for the same
#          vendor, reuse that version's final report instantly (skip pipeline).
#   OFF (default) → always run the full pipeline.
from webapp.settings_store import get_settings as _get_settings
_initial = _get_settings()
LLM_JUDGE_ENABLED: bool = _initial["llm_judge_enabled"]
LLM_CACHE_ENABLED: bool = _initial["llm_cache_enabled"]
