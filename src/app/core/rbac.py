"""RBAC (Role-Based Access Control) FastAPI dependencies.

Usage:
    @router.get("/admin/endpoint")
    async def admin_endpoint(admin: AdminUser):
        ...

    @router.get("/operation/endpoint")
    async def operation_endpoint(user: AdminOrOperationUser):
        ...
"""
from __future__ import annotations

import hashlib
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db
from ..models.enums import UserRole
from ..models.user import User
from ..repositories.user_repository import UserRepository
from .config import Settings, get_settings
from .exceptions import ForbiddenError, UnauthorizedError
from .security import _decode_jwt

logger = structlog.get_logger(__name__)


async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode JWT and return the active User record.

    Raises:
        UnauthorizedError: Missing/invalid/expired token, or user not found.
        ForbiddenError: User account is inactive.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise UnauthorizedError(
            message="Missing or invalid Authorization header",
            error_code="UNAUTHORIZED",
        )

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedError(message="Missing access token", error_code="UNAUTHORIZED")

    payload = _decode_jwt(token, settings=settings)

    phone = payload.get("sub")
    if not isinstance(phone, str) or not phone:
        raise UnauthorizedError(message="Invalid token subject", error_code="INVALID_TOKEN")

    user = await UserRepository(db).get_by_phone(phone)

    if not user:
        # Never log the actual phone number (PII).  A short SHA-256 prefix is
        # sufficient for correlating incidents without exposing the number.
        _ph = hashlib.sha256(phone.encode()).hexdigest()[:12]
        logger.warning("User not found in users table", phone_hash=_ph)
        raise UnauthorizedError(
            message="User not found. Please contact administrator.",
            error_code="USER_NOT_FOUND",
        )

    if not user.is_active:
        logger.warning("Inactive user attempted access", user_id=user.id)
        raise ForbiddenError(
            message="Your account has been deactivated. Please contact administrator.",
            error_code="USER_INACTIVE",
        )

    return user


async def require_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Require Admin role. Raises ForbiddenError otherwise."""
    if current_user.role != UserRole.ADMIN.value:
        logger.warning(
            "Non-admin access attempt",
            user_id=current_user.id,
            role=current_user.role,
        )
        raise ForbiddenError(message="Admin access required", error_code="ADMIN_REQUIRED")
    return current_user


async def require_admin_or_operation(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require Admin or Operation role. Raises ForbiddenError otherwise."""
    allowed_roles = (UserRole.ADMIN.value, UserRole.OPERATION.value)
    if current_user.role not in allowed_roles:
        logger.warning(
            "Insufficient role access attempt",
            user_id=current_user.id,
            role=current_user.role,
        )
        raise ForbiddenError(
            message="Admin or operation access required",
            error_code="INSUFFICIENT_PERMISSIONS",
        )
    return current_user


# ---------------------------------------------------------------------------
# Convenient type aliases for endpoint signatures
# ---------------------------------------------------------------------------
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
AdminOrOperationUser = Annotated[User, Depends(require_admin_or_operation)]
