from datetime import datetime
from typing import Optional
from fastapi import Depends, HTTPException, Header, status
from app.core.config import get_settings

settings = get_settings()

VALID_ROLES = {"admin", "analyst"}


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    """Verify API key and return user context.

    The API key is read from the API_KEY setting (environment variable).
    Using SECRET_KEY as an API key has been removed — the two are now separate
    values to eliminate the 'API key == app secret' vulnerability.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    configured_key = settings.API_KEY
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key authentication is not configured on this server.",
        )

    # Constant-time comparison to prevent timing attacks
    import hmac
    if not hmac.compare_digest(x_api_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return {"user_id": "api-user", "role": "analyst"}


def require_role(*roles: str):
    """Dependency factory: require specific roles."""
    async def _check_role(user: dict = Depends(verify_api_key)):
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.get('role')}' not allowed. Required: {roles}",
            )
        return user
    return _check_role
