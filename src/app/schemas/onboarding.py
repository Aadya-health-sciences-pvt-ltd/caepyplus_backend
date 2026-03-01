"""Onboarding schemas.

Pydantic models for CRUD APIs over onboarding tables:
- doctor_identity
- doctor_details
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
# doctor_details
# ---------------------------------------------------------------------------

class DoctorDetailsBase(BaseModel):

    # Block 1: Professional Identity
    full_name: str | None = None
    specialty: str | None = None
    primary_practice_location: str | None = None
    centres_of_practice: list[str] | None = None
    years_of_clinical_experience: int | None = None
    years_post_specialisation: int | None = None

    # Block 2: Credentials & Trust Markers
    year_of_mbbs: int | None = None
    year_of_specialisation: int | None = None
    fellowships: list[str] | None = None
    qualifications: list[str] | None = None
    professional_memberships: list[str] | None = None
    awards_academic_honours: list[str] | None = None

    # Block 3: Clinical Focus & Expertise
    areas_of_clinical_interest: list[str] | None = None
    practice_segments: str | None = None
    conditions_commonly_treated: list[str] | None = None
    conditions_known_for: list[str] | None = None
    conditions_want_to_treat_more: list[str] | None = None

    # Block 4: The Human Side
    training_experience: list[str] | None = None
    motivation_in_practice: list[str] | None = None
    unwinding_after_work: list[str] | None = None
    recognition_identity: list[str] | None = None
    quality_time_interests: list[str] | None = None
    quality_time_interests_text: str | None = None
    professional_achievement: str | None = None
    personal_achievement: str | None = None
    professional_aspiration: str | None = None
    personal_aspiration: str | None = None

    # Block 5: Patient Value & Choice Factors
    what_patients_value_most: str | None = None
    approach_to_care: str | None = None
    availability_philosophy: str | None = None

    # Block 6: Content Seed (repeatable)
    content_seeds: list[dict[str, Any]] | None = None

    # Existing fields (for compatibility)
    gender: str | None = Field(default=None, max_length=20)
    speciality: str | None = Field(default=None, max_length=100)
    sub_specialities: list[str] | None = None
    areas_of_expertise: list[str] | None = None
    registration_number: str | None = Field(default=None, max_length=100)
    medical_council: str | None = Field(default=None, max_length=200, description="Name of the issuing medical council")
    registration_year: int | None = None
    registration_authority: str | None = Field(default=None, max_length=100)
    consultation_fee: float | None = None
    years_of_experience: int | None = None
    conditions_treated: list[str] | None = None
    procedures_performed: list[str] | None = None
    age_groups_treated: list[str] | None = None
    languages_spoken: list[str] | None = None
    achievements: list[dict[str, Any]] | None = None
    publications: list[dict[str, Any]] | None = None
    practice_locations: list[dict[str, Any]] | None = None
    external_links: dict[str, Any] | None = None
    professional_overview: str | None = None
    about_me: str | None = None
    professional_tagline: str | None = None
    media_urls: dict[str, Any] | None = None
    profile_summary: str | None = None

class DoctorDetailsUpsert(DoctorDetailsBase):
    """Payload for creating/updating doctor_details for a doctor_id."""

class DoctorDetailsResponse(DoctorDetailsBase):
    """API response model for doctor_details."""

    model_config = ConfigDict(from_attributes=True)

    detail_id: str
    doctor_id: int
    created_at: datetime
    updated_at: datetime

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

    Includes identity, details, media, and status history.
    """

    identity: DoctorIdentityResponse
    details: DoctorDetailsResponse | None = None
    media: list[DoctorMediaResponse] = []
    status_history: list[DoctorStatusHistoryResponse] = []

