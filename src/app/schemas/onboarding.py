"""Onboarding schemas.

Pydantic models for CRUD APIs over onboarding tables:
- doctor_identity
- doctor_media
- doctor_status_history
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OnboardingStatusEnum(str, Enum):
    """Public enum for onboarding status used by APIs."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"

class DoctorTitleEnum(str, Enum):
    """Public enum for doctor title used by APIs."""

    DR = "dr"
    PROF = "prof"
    PROF_DR = "prof.dr"

# ---------------------------------------------------------------------------
# doctor_identity
# ---------------------------------------------------------------------------

class DoctorIdentityBase(BaseModel):
    title: DoctorTitleEnum | None = None
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone_number: str = Field(min_length=3, max_length=32)
    onboarding_status: OnboardingStatusEnum = Field(default=OnboardingStatusEnum.PENDING)

class DoctorIdentityCreate(DoctorIdentityBase):
    """Payload for creating a doctor_identity."""

    doctor_id: int | None = None

class DoctorIdentityResponse(DoctorIdentityBase):
    """API response model for doctor_identity."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    doctor_id: int
    # Override base fields to allow empty/placeholder values in responses (e.g. OTP-created doctors)
    title: str | None = None  # type: ignore[assignment]
    first_name: str = Field(max_length=100, default="")
    last_name: str = Field(max_length=100, default="")
    email: str = ""
    phone_number: str = Field(max_length=32, default="")
    status_updated_at: datetime | None = None
    status_updated_by: str | None = None
    rejection_reason: str | None = None
    verified_at: datetime | None = None
    is_active: bool
    registered_at: datetime
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

class OnboardingStatusUpdate(BaseModel):
    new_status: OnboardingStatusEnum
    rejection_reason: str | None = None

# ---------------------------------------------------------------------------
# doctor_media
# ---------------------------------------------------------------------------

class DoctorMediaBase(BaseModel):

    field_name: str | None = None
    media_type: str
    media_category: str
    file_uri: str
    file_name: str
    file_size: int | None = None
    mime_type: str | None = None
    is_primary: bool = False
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="media_metadata")

class DoctorMediaCreate(DoctorMediaBase):
    """Payload for creating a doctor_media record."""

class DoctorMediaResponse(DoctorMediaBase):
    """API response model for doctor_media."""

    model_config = ConfigDict(from_attributes=True)

    media_id: str
    doctor_id: int
    upload_date: datetime

# ---------------------------------------------------------------------------
# doctor_status_history
# ---------------------------------------------------------------------------

class DoctorStatusHistoryCreate(BaseModel):
    previous_status: OnboardingStatusEnum | None = None
    new_status: OnboardingStatusEnum
    changed_by: str | None = None
    changed_by_email: str | None = None
    rejection_reason: str | None = None
    notes: str | None = None

class DoctorStatusHistoryResponse(BaseModel):
    """API response model for doctor_status_history."""

    model_config = ConfigDict(from_attributes=True)

    history_id: str
    doctor_id: int
    previous_status: OnboardingStatusEnum | None = None
    new_status: OnboardingStatusEnum
    changed_by: str | None = None
    changed_by_email: str | None = None
    rejection_reason: str | None = None
    notes: str | None = None
    changed_at: datetime

class DoctorWithFullInfoResponse(BaseModel):
    """Aggregated view of a doctor's onboarding data.

    Includes identity, media, and status history.
    """

    identity: DoctorIdentityResponse
    media: list[DoctorMediaResponse] = []
    status_history: list[DoctorStatusHistoryResponse] = []

