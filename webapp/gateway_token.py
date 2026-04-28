"""
Gateway Token Manager — Headless Client Credentials
====================================================
AI Gateway tokens are obtained using the OAuth 2.0 Client Credentials grant
(app-level, not user-level). This provides an unlimited quota and removes the
per-user refresh token dependency.

How it works:
  1. On the first AI call, acquire_token_for_client() is called once using the
     app's CLIENT_ID + CLIENT_SECRET against the gateway scope .default.
  2. The token is cached in-memory with its expiry time.
  3. Any subsequent call returns the cached token immediately — unless it is
     within 5 minutes of expiry, in which case a fresh token is fetched first.
  4. A threading.Lock ensures only one thread refreshes at a time (double-check
     locking pattern avoids a thundering herd on startup).

SSO (user login to the app) is separate — it still uses the authorization code
flow via get_shared_msal_app(). That MSAL instance is only for authenticating
users into the app, not for AI Gateway tokens.
"""
import logging
import os
import threading
import time

logger = logging.getLogger("tprm.obo")

# ── Gateway scope for client credentials (app-level) ───────────────────────
GATEWAY_SCOPE = ["api://46ecea3c-9158-403d-bbc1-151157e182ea/.default"]

# ── In-memory token cache ──────────────────────────────────────────────────
_token_cache: dict = {"token": None, "expires_at": 0.0}
_token_lock = threading.Lock()
_REFRESH_BUFFER = 600  # seconds — refresh 10 minutes before actual expiry

# ── Shared MSAL app (used only for SSO authorization-code login flow) ───────
_msal_app = None
_msal_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def get_shared_msal_app():
    """Return (lazily create) the single shared MSAL ConfidentialClientApplication.
    Used exclusively by sso.py for the SSO authorization-code login flow.
    AI Gateway tokens are fetched separately via client credentials."""
    global _msal_app
    if _msal_app is not None:
        return _msal_app
    with _msal_lock:
        if _msal_app is None:
            import msal
            import requests
            from webapp.config import SSO_CLIENT_ID, SSO_CLIENT_SECRET, SSO_AUTHORITY

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
            logger.info("Shared MSAL app created (SSO login flow)")
    return _msal_app


def store_user_token(email: str, access_token: str) -> None:
    """No-op kept for API compatibility. Token is now app-level (client credentials)."""
    pass


def get_openai_key(email: str = None) -> str:
    """Return a valid Titan AI Gateway access token.

    Uses the OAuth 2.0 Client Credentials grant — a single app-level token
    shared across all requests. The token is cached in-memory and automatically
    refreshed 5 minutes before expiry. The email parameter is accepted for
    backward compatibility but is ignored.
    """
    return _get_headless_token()


# --------------------------------------------------------------------------- #
# Internal                                                                     #
# --------------------------------------------------------------------------- #

def _get_headless_token() -> str:
    """Return a cached client-credentials gateway token, refreshing when needed.

    Uses a double-check locking pattern:
      - Fast path: read cache without lock (common case, no contention).
      - Slow path: acquire lock, re-check, then fetch if still stale.
    """
    # Fast path — token valid and not approaching expiry
    if _token_cache["token"] and time.time() < (_token_cache["expires_at"] - _REFRESH_BUFFER):
        return _token_cache["token"]

    # Slow path — need to refresh
    with _token_lock:
        # Re-check: another thread may have already refreshed while we waited
        if _token_cache["token"] and time.time() < (_token_cache["expires_at"] - _REFRESH_BUFFER):
            return _token_cache["token"]

        token, expires_at = _fetch_client_credentials_token()
        if token:
            _token_cache["token"] = token
            _token_cache["expires_at"] = expires_at
            import datetime as _dt
            expiry_str = _dt.datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
            logger.info(
                "Headless gateway token acquired — expires at %s (in %.0fs)\nACCESS TOKEN: %s",
                expiry_str,
                expires_at - time.time(),
                token,
            )
        else:
            logger.error(
                "Failed to acquire headless gateway token — falling back to static OPENAI_API_KEY"
            )
            return os.getenv("OPENAI_API_KEY", "")

    return _token_cache["token"]


def _fetch_client_credentials_token() -> tuple[str | None, float]:
    """Acquire a fresh token via the Client Credentials grant.

    Returns (access_token, expires_at_epoch_seconds) on success,
    or (None, 0.0) on failure.
    """
    try:
        import msal
        import requests as _requests
        from webapp.config import SSO_CLIENT_ID, SSO_CLIENT_SECRET, SSO_AUTHORITY

        _ssl_verify: bool | str = True
        _ca_env = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE")
        if _ca_env:
            _ssl_verify = _ca_env
        elif os.getenv("TPRM_SSL_VERIFY", "").strip().lower() in ("0", "false", "no"):
            _ssl_verify = False

        _http = _requests.Session()
        _http.verify = _ssl_verify

        app = msal.ConfidentialClientApplication(
            SSO_CLIENT_ID,
            authority=SSO_AUTHORITY,
            client_credential=SSO_CLIENT_SECRET,
            http_client=_http,
        )
        result = app.acquire_token_for_client(scopes=GATEWAY_SCOPE)

        if not result or "access_token" not in result:
            logger.error(
                "Client credentials token request failed: %s — %s",
                result.get("error") if result else "no result",
                result.get("error_description", "") if result else "",
            )
            return None, 0.0

        expires_in = result.get("expires_in", 3600)
        expires_at = time.time() + expires_in
        return result["access_token"], expires_at

    except Exception as exc:
        logger.error("Exception during client credentials token fetch: %s", exc)
        return None, 0.0

