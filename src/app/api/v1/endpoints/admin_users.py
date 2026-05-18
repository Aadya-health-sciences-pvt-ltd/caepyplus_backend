"""
Admin User Management API Endpoints.

Provides endpoints for managing users in the RBAC system:
- List users with filtering
- Create admin/operation users
- Update user roles
- Activate/deactivate users

All endpoints require admin authentication.
"""
from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.rbac import AdminOrOperationUser, AdminUser
from ....core.responses import GenericResponse
from ....db.session import get_db
from ....models.enums import UserRole
from ....repositories.user_repository import UserRepository
from ....schemas.user import (
    UserCreate,
    UserCreateResponse,
    UserDeleteResponse,
    UserListResponse,
    UserResponse,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUpdate,
    UserUpdateResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/users",
    tags=["Admin - User Management"],
)


# =============================================================================
# Dependencies
# =============================================================================

async def get_user_repo(
    db: AsyncSession = Depends(get_db),
) -> UserRepository:
    """Get user repository with database session."""
    return UserRepository(db)


# =============================================================================
# LIST ENDPOINTS
# =============================================================================

@router.get(
    "",
    response_model=GenericResponse[UserListResponse],
    summary="List all users",
    description="Get paginated list of users with optional filtering by role and status.",
)
async def list_users(
    current_user: AdminOrOperationUser,
    repo: UserRepository = Depends(get_user_repo),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Number of records to return"),
    role: list[str] | None = Query(None, description="Filter by role (admin, operation, user)"),
    is_active: bool | None = Query(None, description="Filter by active status"),
) -> GenericResponse[UserListResponse]:
    """List all users with pagination and optional filtering."""
    # Run the page query and total count query concurrently.
    users, total = await asyncio.gather(
        repo.get_all(skip=skip, limit=limit, role=role, is_active=is_active),
        repo.count_all(role=role, is_active=is_active),
    )

    return GenericResponse(
        message=f"Found {total} user(s)",
        data=UserListResponse(
            success=True,
            users=[UserResponse.model_validate(u) for u in users],
            total=total,
            skip=skip,
            limit=limit,
        ),
    )


@router.get(
    "/admins",
    response_model=GenericResponse[UserListResponse],
    summary="List admin users",
    description="Get all admin users (for audit purposes).",
)
async def list_admins(
    admin: AdminUser,
    repo: UserRepository = Depends(get_user_repo),
    active_only: bool = Query(True, description="Only show active admins"),
) -> GenericResponse[UserListResponse]:
    """List all admin users."""
    admins = await repo.get_admins(active_only=active_only)

    return GenericResponse(
        message=f"Found {len(admins)} admin user(s)",
        data=UserListResponse(
            success=True,
            users=[UserResponse.model_validate(u) for u in admins],
            total=len(admins),
            skip=0,
            limit=len(admins),
        ),
    )


@router.get(
    "/{user_id}",
    response_model=GenericResponse[UserResponse],
    summary="Get user by ID",
    description="Get details of a specific user.",
)
async def get_user(
    user_id: int,
    current_user: AdminOrOperationUser,
    repo: UserRepository = Depends(get_user_repo),
) -> GenericResponse[UserResponse]:
    """Get a specific user by ID."""
    user = await repo.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "User not found"},
        )

    return GenericResponse(
        message="User retrieved successfully",
        data=UserResponse.model_validate(user),
    )


# =============================================================================
# CREATE ENDPOINTS
# =============================================================================

@router.post(
    "/seed",
    response_model=GenericResponse[UserCreateResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Seed initial admin user (no auth required)",
    description=(
        "Create the first admin user(s) when no admins exist in the database. "
        "This endpoint is publicly accessible but **self-disabling**: once at least "
        "one active admin user exists, it returns 403. Use this only for initial setup."
    ),
)
async def seed_admin_user(
    payload: UserCreate,
    repo: UserRepository = Depends(get_user_repo),
) -> GenericResponse[UserCreateResponse]:
    """Seed initial admin — no auth required, disabled once an admin exists."""
    # Check if any admin users already exist
    existing_admins = await repo.get_admins(active_only=False)
    if existing_admins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": (
                    "Admin users already exist. Use the authenticated "
                    "POST /admin/users endpoint instead."
                ),
            },
        )

    # Force role to admin for seeding
    payload_role = payload.role
    if payload_role != UserRole.ADMIN.value:
        logger.info("Seed endpoint overriding role to admin", original_role=payload_role)

    # Check for duplicate phone.
    # The /seed endpoint is public — do NOT expose existing_user_id in the
    # error response, as that enables unauthenticated user enumeration.
    existing = await repo.get_by_phone(payload.phone)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "success": False,
                "message": "User with this phone number already exists",
            },
        )

    # Check for duplicate email
    if payload.email:
        existing_email = await repo.get_by_email(payload.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "success": False,
                    "message": "User with this email already exists",
                },
            )

    user = await repo.create(
        phone=payload.phone,
        email=payload.email,
        full_name=payload.full_name,
        role=UserRole.ADMIN.value,  # Always admin for seed
        is_active=True,
        doctor_id=payload.doctor_id,
    )

    logger.info("Seeded initial admin user", user_id=user.id)

    return GenericResponse(
        message="Initial admin user seeded successfully",
        data=UserCreateResponse(
            success=True,
            message="Initial admin user seeded successfully",
            user=UserResponse.model_validate(user),
        ),
    )


@router.post(
    "",
    response_model=GenericResponse[UserCreateResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin only)",
    description="Create a new user with specified role. Only admins can access this endpoint.",
)
async def create_user(
    payload: UserCreate,
    admin: AdminUser,
    repo: UserRepository = Depends(get_user_repo),
) -> GenericResponse[UserCreateResponse]:
    """Create a new user — requires admin authentication."""
    # Check if phone already exists
    existing = await repo.get_by_phone(payload.phone)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "success": False,
                "message": "User with this phone number already exists",
                "existing_user_id": existing.id,
            },
        )

    # Check if email already exists
    if payload.email:
        existing_email = await repo.get_by_email(payload.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "success": False,
                    "message": "User with this email already exists",
                    "existing_user_id": existing_email.id,
                },
            )

    user = await repo.create(
        phone=payload.phone,
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
        doctor_id=payload.doctor_id,
    )

    logger.info("Admin created user", admin_id=admin.id, user_id=user.id, role=payload.role)

    return GenericResponse(
        message=f"User created successfully with role '{payload.role}'",
        data=UserCreateResponse(
            success=True,
            message=f"User created successfully with role '{payload.role}'",
            user=UserResponse.model_validate(user),
        ),
    )


# =============================================================================
# UPDATE ENDPOINTS
# =============================================================================

@router.patch(
    "/{user_id}",
    response_model=GenericResponse[UserUpdateResponse],
    summary="Update user",
    description="Update user details. Only admins can modify user records.",
)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    admin: AdminUser,
    repo: UserRepository = Depends(get_user_repo),
) -> GenericResponse[UserUpdateResponse]:
    """Update a user's details."""
    user = await repo.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "User not found"},
        )

    # Prevent self-demotion (admin can't remove their own admin role)
    if user_id == admin.id and payload.role and payload.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "message": "Cannot demote yourself. Ask another admin.",
            },
        )

    # Prevent self-deactivation
    if user_id == admin.id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "message": "Cannot deactivate yourself. Ask another admin.",
            },
        )

    # Apply all requested changes in a single transaction so the row is never
    # left in a partially-updated state (e.g. role changed but is_active not).
    user = await repo.update_fields(
        user_id,
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
        doctor_id=payload.doctor_id,
    )

    logger.info("Admin updated user", admin_id=admin.id, user_id=user_id)

    return GenericResponse(
        message="User updated successfully",
        data=UserUpdateResponse(
            success=True,
            message="User updated successfully",
            user=UserResponse.model_validate(user),
        ),
    )


@router.patch(
    "/{user_id}/role",
    response_model=GenericResponse[UserUpdateResponse],
    summary="Update user role",
    description="Change a user's role (admin, operation, user).",
)
async def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    admin: AdminUser,
    repo: UserRepository = Depends(get_user_repo),
) -> GenericResponse[UserUpdateResponse]:
    """Update a user's role."""
    user = await repo.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "User not found"},
        )

    # Prevent self-demotion
    if user_id == admin.id and payload.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "message": "Cannot demote yourself. Ask another admin.",
            },
        )

    old_role = user.role
    user = await repo.update_role(user_id, payload.role)

    logger.info("Admin changed user role", admin_id=admin.id, user_id=user_id, old_role=old_role, new_role=payload.role)

    return GenericResponse(
        message=f"User role changed from '{old_role}' to '{payload.role}'",
        data=UserUpdateResponse(
            success=True,
            message=f"User role changed from '{old_role}' to '{payload.role}'",
            user=UserResponse.model_validate(user),
        ),
    )


@router.patch(
    "/{user_id}/status",
    response_model=GenericResponse[UserUpdateResponse],
    summary="Activate/deactivate user",
    description="Activate or deactivate a user (soft delete).",
)
async def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    admin: AdminUser,
    repo: UserRepository = Depends(get_user_repo),
) -> GenericResponse[UserUpdateResponse]:
    """Activate or deactivate a user."""
    user = await repo.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "User not found"},
        )

    # Prevent self-deactivation
    if user_id == admin.id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "message": "Cannot deactivate yourself. Ask another admin.",
            },
        )

    user = await repo.set_active(user_id, payload.is_active)
    status_text = "activated" if payload.is_active else "deactivated"

    logger.info("Admin changed user status", admin_id=admin.id, user_id=user_id, new_status=status_text)

    return GenericResponse(
        message=f"User {status_text} successfully",
        data=UserUpdateResponse(
            success=True,
            message=f"User {status_text} successfully",
            user=UserResponse.model_validate(user),
        ),
    )


# =============================================================================
# DELETE ENDPOINTS
# =============================================================================

@router.delete(
    "/{user_id}",
    response_model=GenericResponse[UserDeleteResponse],
    summary="Deactivate user (soft delete)",
    description="Deactivate a user. Use this instead of hard delete to preserve audit trail.",
)
async def deactivate_user(
    user_id: int,
    admin: AdminUser,
    repo: UserRepository = Depends(get_user_repo),
) -> GenericResponse[UserDeleteResponse]:
    """Deactivate a user (soft delete)."""
    user = await repo.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "User not found"},
        )

    # Prevent self-deactivation
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "message": "Cannot deactivate yourself. Ask another admin.",
            },
        )

    await repo.deactivate(user_id)

    logger.info("Admin deactivated user", admin_id=admin.id, user_id=user_id)

    return GenericResponse(
        message="User deactivated successfully",
        data=UserDeleteResponse(
            success=True,
            message="User deactivated successfully",
            user_id=user_id,
        ),
    )
