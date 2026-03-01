"""Onboarding schema models (PostgreSQL).

Implements the core onboarding tables from DATABASE_DESIGN.md:
- doctor_identity
- doctor_details
- doctor_media
- doctor_status_history
- dropdown_options (for configurable dropdown values)

These models are designed to work with PostgreSQL via the shared SQLAlchemy Base.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.session import Base


def utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class OnboardingStatus(str, Enum):
    """Onboarding status enum used by doctor_identity.

    Allowed values: pending, submitted, verified, rejected.
    """

    PENDING = "pending"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"


class DoctorTitle(str, Enum):
    """Doctor title enum used by doctor_identity.

    Allowed values: dr, prof, prof.dr.
    """

    DR = "dr"
    PROF = "prof"
    PROF_DR = "prof.dr"


class DoctorIdentity(Base):
    """doctor_identity table - basic identification and contact information."""

    __tablename__ = "doctor_identity"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    doctor_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
    )

    title: Mapped[DoctorTitle | None] = mapped_column(
        SQLEnum(DoctorTitle, name="doctor_title_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)

    onboarding_status: Mapped[OnboardingStatus] = mapped_column(
        SQLEnum(OnboardingStatus, name="onboarding_status_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=OnboardingStatus.PENDING,
        index=True,
    )

    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_updated_by: Mapped[str | None] = mapped_column(String(36))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    details: Mapped[DoctorDetails] = relationship(
        back_populates="identity",
        uselist=False,
        cascade="all, delete-orphan",
    )
    media: Mapped[list[DoctorMedia]] = relationship(
        back_populates="identity",
        cascade="all, delete-orphan",
    )
    status_history: Mapped[list[DoctorStatusHistory]] = relationship(
        back_populates="identity",
        cascade="all, delete-orphan",
    )

class DoctorDetails(Base):
    """doctor_details table - comprehensive professional information."""

    __tablename__ = "doctor_details"

    detail_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    doctor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("doctor_identity.doctor_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Block 1: Professional Identity
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    specialty: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary_practice_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    centres_of_practice: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    years_of_clinical_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    years_post_specialisation: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Block 2: Credentials & Trust Markers
    year_of_mbbs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_of_specialisation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fellowships: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    qualifications: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    professional_memberships: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    awards_academic_honours: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Block 3: Clinical Focus & Expertise
    areas_of_clinical_interest: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    practice_segments: Mapped[str | None] = mapped_column(String(50), nullable=True)
    conditions_commonly_treated: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    conditions_known_for: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    conditions_want_to_treat_more: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Block 4: The Human Side
    training_experience: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    motivation_in_practice: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    unwinding_after_work: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    recognition_identity: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    quality_time_interests: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    quality_time_interests_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    professional_achievement: Mapped[str | None] = mapped_column(Text, nullable=True)
    personal_achievement: Mapped[str | None] = mapped_column(Text, nullable=True)
    professional_aspiration: Mapped[str | None] = mapped_column(Text, nullable=True)
    personal_aspiration: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Block 5: Patient Value & Choice Factors
    what_patients_value_most: Mapped[str | None] = mapped_column(Text, nullable=True)
    approach_to_care: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability_philosophy: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Block 6: Content Seed (repeatable)
    content_seeds: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    # Existing fields (for compatibility)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    speciality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sub_specialities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    areas_of_expertise: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    medical_council: Mapped[str | None] = mapped_column(String(200), nullable=True)
    registration_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registration_authority: Mapped[str | None] = mapped_column(String(100), nullable=True)
    consultation_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    years_of_experience: Mapped[int | None] = mapped_column(Integer)
    conditions_treated: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    procedures_performed: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    age_groups_treated: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    languages_spoken: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    achievements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    publications: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    practice_locations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    external_links: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    professional_overview: Mapped[str | None] = mapped_column(Text)
    about_me: Mapped[str | None] = mapped_column(Text)
    professional_tagline: Mapped[str | None] = mapped_column(Text)

    media_urls: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    profile_summary: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    identity: Mapped[DoctorIdentity] = relationship(back_populates="details")


class DoctorMedia(Base):
    """doctor_media table - references to media files (URIs/metadata)."""

    __tablename__ = "doctor_media"

    media_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    doctor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("doctor_identity.doctor_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    media_type: Mapped[str] = mapped_column(String(50), nullable=False)
    media_category: Mapped[str] = mapped_column(String(50), nullable=False)

    file_uri: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)

    file_size: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(100))

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    upload_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    media_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    identity: Mapped[DoctorIdentity] = relationship(back_populates="media")


class DropdownOptionStatus(str, Enum):
    """Approval status for a user-submitted dropdown option.

    - APPROVED  : visible in all public-facing dropdowns (seed data starts here)
    - PENDING   : submitted by a doctor/user; hidden until admin approves
    - REJECTED  : admin-rejected; never shown to end users
    """

    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"


class DropdownOption(Base):
    """dropdown_options table - configurable dropdown values by field.

    Stores curated values for dropdown fields (e.g., specialisations,
    qualifications, languages) used by the onboarding forms.

    Workflow
    --------
    * Seed / admin-added rows start with ``status = APPROVED``.
    * Doctor/user-submitted rows start with ``status = PENDING`` and are
      hidden from public dropdowns until an Admin or Operational user
      approves them.
    * The unique constraint on (field_name, value) makes inserts idempotent.

    All columns (including the approval-workflow fields) were created in
    the consolidated 001_initial_schema migration.
    """

    __tablename__ = "dropdown_options"
    __table_args__ = (
        UniqueConstraint("field_name", "value", name="uq_dropdown_field_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)

    # Human-readable display label (defaults to value when not set)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Approval workflow
    status: Mapped[DropdownOptionStatus] = mapped_column(
        SQLEnum(DropdownOptionStatus, name="dropdown_option_status_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DropdownOptionStatus.APPROVED,
        index=True,
    )

    # System / seed rows cannot be deleted by users
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Display ordering within a field (lower = first)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Who submitted this option (for PENDING rows)
    submitted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    submitted_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Who reviewed this option (admin/operational user)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class DoctorStatusHistory(Base):
    """doctor_status_history table - audit log of status changes."""

    __tablename__ = "doctor_status_history"

    history_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    doctor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("doctor_identity.doctor_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    previous_status: Mapped[OnboardingStatus | None] = mapped_column(
        SQLEnum(OnboardingStatus, name="onboarding_status_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    new_status: Mapped[OnboardingStatus] = mapped_column(
        SQLEnum(OnboardingStatus, name="onboarding_status_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    changed_by: Mapped[str | None] = mapped_column(String(36))
    changed_by_email: Mapped[str | None] = mapped_column(String(255))

    rejection_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    ip_address: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(Text)

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    identity: Mapped[DoctorIdentity] = relationship(back_populates="status_history")
