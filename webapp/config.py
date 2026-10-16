"""
Web App Configuration
=====================
"""

import os
import secrets as _secrets
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient

SSO_TENANT_ID = os.getenv("TENANT_ID", "7cc91c38-648e-4ce2-a4e4-517ae39fc189").strip()
print("TENANT_ID",SSO_TENANT_ID)
CLIENT_ID= os.getenv("CLIENT_ID")
# Project root and environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# Azure Key Vault configuration
VAULT_URL = os.getenv(
    "KEY_VAULT_URL",
    "https://tclkeyvaultinfosec.vault.azure.net"
)
CERTIFICATE_KEY = os.getenv("CERTIFICATE_KEY", "your-keyvault-secret-name")


CLIENT_SECRET_KEY = os.getenv("CLIENT_SECRET_KEY", "")
CERTIFICATE_KEY =  os.getenv("CERTIFICATE_KEY", "")
CLIENT_ID_KEY =  os.getenv("CLIENT_ID_KEY", "")

is_dev = os.getenv("ENV", "DEV").upper() == "DEV"


def get_keyvault_client():

    credential = ManagedIdentityCredential()
    return SecretClient(
        vault_url=VAULT_URL,
        credential=credential
    )


def get_secret(secret_type: Literal["client_secret", "client_id", "certificate"]):
    match secret_type:
        case "client_secret":
            if is_dev:
                client_secret = os.getenv("AUTH_CLIENT_SECRET")
            else:
                client = get_keyvault_client()

                try:
                    client_secret = client.get_secret(
                        CLIENT_SECRET_KEY
                    ).value
                except ResourceNotFoundError as exc:
                    raise RuntimeError(
                        f"Secret '{CLIENT_SECRET_KEY}' not found in Key Vault"
                    ) from exc

            if not client_secret:
                raise RuntimeError(
                    f"Client Secret not found in "
                    f"{'env' if is_dev else 'vault'}"
                )

            return client_secret
        case "client_id":
            if is_dev:
                client_id = os.getenv("CLIENT_ID")
            else:
                client = get_keyvault_client()

                try:
                    client_id = client.get_secret(
                        CLIENT_ID_KEY
                    ).value
                except ResourceNotFoundError as exc:
                    raise RuntimeError(
                        f"Secret '{CLIENT_ID_KEY}' not found in Key Vault"
                    ) from exc

            if not client_id:
                raise RuntimeError(
                    f"Client ID not found in "
                    f"{'env' if is_dev else 'vault'}"
                )
            print("CLIENT_ID",client_id)
            return client_id
            
        case "certificate":
            client = get_keyvault_client()
            try:
                certificate = client.get_secret(
                    CERTIFICATE_KEY
                ).value
            except ResourceNotFoundError as exc:
                raise RuntimeError(
                    f"Secret '{CERTIFICATE_KEY}' not found in Key Vault"
                ) from exc

            if not certificate:
                raise RuntimeError(
                    f"Certificate not found in "
                    f"{'env' if is_dev else 'vault'}"
                )
            return certificate

        case _:
            raise ValueError("Invalid Secret Type passed")


# Directories
ASSESSMENTS_DIR = PROJECT_ROOT / "assessments"
ASSESSMENTS_DIR.mkdir(exist_ok=True)


# App settings
APP_NAME = "TPRM AI Assessment Platform"
APP_VERSION = "1.0.0"

HOST = os.getenv("TPRM_HOST", "127.0.0.1")
PORT = int(os.getenv("TPRM_PORT", "8085"))
DEBUG = os.getenv("TPRM_DEBUG", "false").lower() == "true"


# SECRET_KEY
SECRET_KEY = os.getenv("SECRET_KEY") or _secrets.token_hex(32)


# Azure AD SSO
SSO_ENABLED = os.getenv("SSO_ENABLED", "true").lower() == "true"
SSO_CLIENT_ID_LOCAL = os.getenv("CLIENT_ID", "").strip()
SSO_CERTIFICATE = get_secret("certificate")
SSO_CLIENT_ID = get_secret("client_id")
SSO_CLIENT_SECRET=""

SSO_REDIRECT_URI = os.getenv(
    "REDIRECT_URI",
    "http://localhost:8085/auth/callback"
)

SSO_AUTHORITY = (
    f"https://login.microsoftonline.com/{SSO_TENANT_ID}"
    if SSO_TENANT_ID
    else ""
)
print("SSO_AUTHORITUY", SSO_AUTHORITY)
SSO_SCOPES = [
    "api://46ecea3c-9158-403d-bbc1-151157e182ea/access_as_user",
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


    
