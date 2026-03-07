"""
User Schemas for RBAC.

Pydantic models for user management requests and responses.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.enums import UserRole


def _validate_user_role(v: str) -> str:
    """Validate that *v* is an allowed UserRole value.

    Centralised so every schema that validates a role field delegates here
    instead of duplicating the check.
    """
    allowed = [r.value for r in UserRole]
    if v not in allowed:
        raise ValueError(f"Role must be one of: {', '.join(allowed)}")
    return v


# =============================================================================
# REQUEST SCHEMAS
# =============================================================================

class UserCreate(BaseModel):
    """Schema for creating a new user."""

    full_name: str | None = Field(
        None,
        description="Full name of the user",
        examples=["John Doe"],
    )
    phone: str = Field(
        ...,
        description="Phone number (10 digits or with +91 prefix)",
        examples=["9988776655", "+919988776655"],
    )
    email: str | None = Field(
        None,
        description="Optional email address",
        examples=["user@example.com"],
    )
    role: str = Field(
        default=UserRole.USER.value,
        description="User role: admin, operation, user",
        examples=["user", "admin"],
    )
    is_active: bool = Field(
        default=True,
        description="Whether the user is active",
    )
    doctor_id: int | None = Field(
        None,
        description="Optional link to doctor record",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is one of the allowed values."""
        return _validate_user_role(v)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Basic phone validation."""
        digits = ''.join(c for c in v if c.isdigit())
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return v

    @field_validator("doctor_id")
    @classmethod
    def validate_doctor_id(cls, v: int | None) -> int | None:
        """Convert 0 to None for doctor_id to prevent foreign key errors."""
        return None if v == 0 else v


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    full_name: str | None = Field(
        None,
        description="Updated full name",
    )
    email: str | None = Field(
        None,
        description="Updated email address",
    )
    role: str | None = Field(
        None,
        description="Updated role: admin, operation, user",
    )
    is_active: bool | None = Field(
        None,
        description="Updated active status",
    )
    doctor_id: int | None = Field(
        None,
        description="Updated doctor link",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        """Validate role if provided."""
        if v is not None:
            return _validate_user_role(v)
        return v

    @field_validator("doctor_id")
    @classmethod
    def validate_doctor_id(cls, v: int | None) -> int | None:
        """Convert 0 to None for doctor_id to prevent foreign key errors."""
        return None if v == 0 else v


class UserRoleUpdate(BaseModel):
    """Schema for updating only user's role."""

    role: str = Field(
        ...,
        description="New role: admin, operation, user",
        examples=["admin"],
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is one of the allowed values."""
        return _validate_user_role(v)


class UserStatusUpdate(BaseModel):
    """Schema for activating/deactivating a user."""

    is_active: bool = Field(
        ...,
        description="True to activate, False to deactivate",
    )


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================

class UserResponse(BaseModel):
    """Schema for user response."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="User ID")
    full_name: str | None = Field(None, description="Full name")
    phone: str = Field(..., description="Phone number")
    email: str | None = Field(None, description="Email address")
    role: str = Field(..., description="User role")
    is_active: bool = Field(..., description="Active status")
    doctor_id: int | None = Field(None, description="Linked doctor ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")
    last_login_at: datetime | None = Field(None, description="Last login timestamp")


class UserListResponse(BaseModel):
    """Schema for paginated user list response."""

    success: bool = Field(default=True)
    users: list[UserResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total count")
    skip: int = Field(..., description="Offset")
    limit: int = Field(..., description="Page size")


class UserCreateResponse(BaseModel):
    """Schema for user creation response."""

    success: bool = Field(default=True)
    message: str = Field(default="User created successfully")
    user: UserResponse = Field(..., description="Created user")


class UserUpdateResponse(BaseModel):
    """Schema for user update response."""

    success: bool = Field(default=True)
    message: str = Field(default="User updated successfully")
    user: UserResponse = Field(..., description="Updated user")


class UserDeleteResponse(BaseModel):
    """Schema for user deletion response."""

    success: bool = Field(default=True)
    message: str = Field(default="User deactivated successfully")
    user_id: int = Field(..., description="Deactivated user ID")
