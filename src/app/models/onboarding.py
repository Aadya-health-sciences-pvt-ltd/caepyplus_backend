"""Onboarding schema models (PostgreSQL).

Implements the core onboarding tables:
- doctor_identity
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

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
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

    media: Mapped[list[DoctorMedia]] = relationship(
        back_populates="identity",
        cascade="all, delete-orphan",
    )
    status_history: Mapped[list[DoctorStatusHistory]] = relationship(
        back_populates="identity",
        cascade="all, delete-orphan",
    )

# DoctorDetails table removed — professional data is stored in the doctors table.

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
      hidden from public dropdowns until an Admin or Operation user
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

    # Who reviewed this option (admin/operation user)
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
