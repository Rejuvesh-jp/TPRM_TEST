"""
Gateway Token Manager — Silent Refresh via Shared MSAL Instance
===============================================================
How it works:

  1. User signs in via SSO. sso.py calls acquire_token_by_authorization_code()
     on the shared MSAL instance → MSAL stores the account + refresh token in cache.

  2. Before every AI call, get_openai_key() calls acquire_token_silent() on the
     same shared MSAL instance. MSAL returns the cached access token if still valid,
     or silently exchanges the refresh token for a fresh one if expired.

  3. Falls back to the static OPENAI_API_KEY from .env for form-login sessions.

NOTE: OBO (On-Behalf-Of) is NOT used here. OBO requires a token scoped to OUR
app as the user_assertion. The SSO access_token is already scoped to the gateway,
so MSAL's built-in silent refresh is the correct mechanism.
"""
import logging
import os
import threading

logger = logging.getLogger("tprm.obo")

# The gateway scope we requested during SSO login
GATEWAY_SCOPE = ["api://46ecea3c-9158-403d-bbc1-151157e182ea/access_as_user"]

# Single shared MSAL ConfidentialClientApplication.
# MUST be the same instance used in sso.py — token cache lives here.
_msal_app = None
_msal_lock = threading.Lock()


def get_shared_msal_app():
    """Return (lazily create) the single shared MSAL ConfidentialClientApplication."""
    global _msal_app
    if _msal_app is not None:
        return _msal_app
    with _msal_lock:
        if _msal_app is None:
            import msal
            import requests
            import os
            from webapp.config import SSO_CLIENT_ID, SSO_CLIENT_SECRET, SSO_AUTHORITY

            # Corporate proxies may replace SSL certs; honour REQUESTS_CA_BUNDLE
            # or fall back to certifi + the system store.  If nothing works the
            # user can set TPRM_SSL_VERIFY=false for local development only.
            _ssl_verify: bool | str = True
            _ca_env = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE")
            if _ca_env:
                _ssl_verify = _ca_env
            elif os.getenv("TPRM_SSL_VERIFY", "").strip().lower() in ("0", "false", "no"):
                _ssl_verify = False
                logger.warning("SSL verification DISABLED for MSAL (TPRM_SSL_VERIFY=false)")

            _http = requests.Session()
            _http.verify = _ssl_verify

            _msal_app = msal.ConfidentialClientApplication(
                SSO_CLIENT_ID,
                authority=SSO_AUTHORITY,
                client_credential=SSO_CLIENT_SECRET,
                http_client=_http,
            )
            logger.info("Shared MSAL app created")
    return _msal_app


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def store_user_token(email: str, access_token: str) -> None:
    """No-op kept for API compatibility. MSAL account cache is the source of truth."""
    pass  # MSAL stores the account in its cache during acquire_token_by_authorization_code


def get_openai_key(email: str = None) -> str:
    """
    Return the best available API key for the Titan AI Gateway.

    Priority:
    1. Silently refreshed gateway token via MSAL account cache (SSO users).
    2. Static OPENAI_API_KEY from .env (form-login users / fallback).
    """
    if email:
        token = _get_gateway_token_silent(email.lower())
        if token:
            return token
        logger.warning("No MSAL account for %s — falling back to static key", email)
    return os.getenv("OPENAI_API_KEY", "")


# --------------------------------------------------------------------------- #
# Internal                                                                     #
# --------------------------------------------------------------------------- #

def _get_gateway_token_silent(email: str) -> str | None:
    """
    Use MSAL's account cache to silently get a fresh gateway access token.
    MSAL automatically uses the stored refresh token when the access token expires.
    Both sso.py (populate) and this function (consume) use get_shared_msal_app()
    so they share the same cache.
    """
    try:
        app = get_shared_msal_app()
        all_accounts = app.get_accounts()
        if not all_accounts:
            logger.debug("MSAL cache empty — no accounts found")
            return None

        # Case-insensitive match on username (upn/preferred_username)
        account = next(
            (a for a in all_accounts
             if a.get("username", "").lower() == email),
            None,
        )
        if not account:
            logger.warning(
                "No MSAL account for %s. Cached accounts: %s",
                email, [a.get("username") for a in all_accounts],
            )
            return None

        result = app.acquire_token_silent(GATEWAY_SCOPE, account=account)
        if result and "access_token" in result:
            logger.info("Gateway token silently refreshed for %s", email)
            return result["access_token"]

        if result:
            logger.warning(
                "Silent refresh failed for %s: %s — %s",
                email, result.get("error"), result.get("error_description"),
            )
        return None
    except Exception as exc:
        logger.error("Silent refresh error for %s: %s", email, exc)
        return None

