"""
User Management Routes
======================
Admin users can manage application users stored in the app_users database table.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, validator

from webapp.auth import (
    get_session, login_redirect,
    add_user, hash_password, validate_password_complexity,
)
from webapp.routes.pages import templates, _ctx

logger = logging.getLogger("tprm.user_mgmt")

router = APIRouter()


# --------------------------------------------------------------------------- #
# Helper                                                                       #
# --------------------------------------------------------------------------- #

def _require_admin(request: Request) -> dict:
    """Require admin authentication.  Raises HTTP 401/403 otherwise."""
    user = get_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def _db():
    from webapp.db import SessionLocal
    return SessionLocal()


# --------------------------------------------------------------------------- #
# Pydantic models                                                              #
# --------------------------------------------------------------------------- #

class UserCreateRequest(BaseModel):
    email: EmailStr
    name: str
    role: str
    password: str

    @validator("name")
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    @validator("role")
    def role_valid(cls, v):
        if v not in ("admin", "analyst"):
            raise ValueError("Role must be admin or analyst")
        return v

    @validator("password")
    def password_complexity(cls, v):
        errors = validate_password_complexity(v)
        if errors:
            raise ValueError("Password must have: " + ", ".join(errors))
        return v


class UserUpdateRequest(BaseModel):
    name: str = None
    role: str = None
    password: str = None

    @validator("name")
    def name_not_empty(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip() if v else v

    @validator("role")
    def role_valid(cls, v):
        if v is not None and v not in ("admin", "analyst"):
            raise ValueError("Role must be admin or analyst")
        return v

    @validator("password")
    def password_complexity(cls, v):
        if v is not None:
            errors = validate_password_complexity(v)
            if errors:
                raise ValueError("Password must have: " + ", ".join(errors))
        return v


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #

@router.get("/admin/users")
async def user_management_page(request: Request):
    """User management interface."""
    user = get_session(request)
    if not user:
        return login_redirect()
    if user.get("role") != "admin":
        return templates.TemplateResponse(
            "error.html", _ctx(request, {"error": "Admin access required"})
        )
    return templates.TemplateResponse("user_management.html", _ctx(request))


@router.get("/api/users")
async def list_users(request: Request):
    """List all users (password excluded) -- Admin only."""
    _require_admin(request)
    from webapp.models import AppUser
    with _db() as session:
        rows = session.query(AppUser).filter(AppUser.is_active == True).all()
        users = [
            {
                "email":      r.email,
                "name":       r.name,
                "role":       r.role,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    return JSONResponse({"users": users})


@router.post("/api/users")
async def create_user(request: Request, user_data: UserCreateRequest):
    """Create a new user -- Admin only."""
    current_user = _require_admin(request)
    if add_user(user_data.email, user_data.name, user_data.password, user_data.role):
        logger.info("User %s created by %s", user_data.email, current_user["email"])
        return JSONResponse(
            {"success": True, "message": f"User {user_data.email} created successfully"}
        )
    raise HTTPException(
        status_code=409,
        detail="User with this email already exists or creation failed",
    )


@router.put("/api/users/{email}")
async def update_user(request: Request, email: str, user_data: UserUpdateRequest):
    """Update an existing user -- Admin only."""
    current_user = _require_admin(request)
    from webapp.models import AppUser
    now = datetime.now(timezone.utc).isoformat()
    with _db() as session:
        row = session.query(AppUser).filter(AppUser.email.ilike(email)).first()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        if user_data.name is not None:
            row.name = user_data.name
        if user_data.role is not None:
            row.role = user_data.role
        if user_data.password is not None:
            row.password_hash = hash_password(user_data.password)
        row.updated_at = now
        session.commit()
    logger.info("User %s updated by %s", email, current_user["email"])
    return JSONResponse({"success": True, "message": f"User {email} updated successfully"})


@router.delete("/api/users/{email}")
async def delete_user(request: Request, email: str):
    """Delete a user -- Admin only.  Cannot delete own account."""
    current_user = _require_admin(request)
    if current_user["email"].lower() == email.lower():
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    from webapp.models import AppUser
    with _db() as session:
        row = session.query(AppUser).filter(AppUser.email.ilike(email)).first()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        session.delete(row)
        session.commit()
    logger.info("User %s deleted by %s", email, current_user["email"])
    return JSONResponse({"success": True, "message": f"User {email} deleted successfully"})


@router.get("/api/users/audit")
async def get_audit_log(request: Request):
    """Get login activity audit log -- Admin only."""
    _require_admin(request)
    from webapp.auth import get_login_activity
    return JSONResponse({"audit_log": get_login_activity()})
