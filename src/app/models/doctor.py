"""
Doctor Domain Models.

SQLAlchemy 2.0 ORM models for the doctors domain.

Architecture:
    - Doctor: Primary entity storing professional information
    - Qualification: Related entity (1:N relationship) for educational credentials
    
Design Decisions:
    - JSON columns for variable-length arrays (languages, awards, etc.)
    - Separate Qualification table for normalized degree storage
    - Cascade delete for qualifications when doctor is deleted
    - selectin loading for eager-loading relationships by default
    
SQLAlchemy 2.0 Features Used:
    - Mapped[] type annotations
    - mapped_column() for column definitions
    - relationship() with type hints
    - No legacy Query API (uses select() statements)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .user import User

# Use JSON type - SQLAlchemy handles dialect differences automatically
# PostgreSQL: Uses JSONB, SQLite: Uses JSON
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.session import Base


class Doctor(Base):
    """
    Doctor entity - Primary aggregate root for doctor onboarding.
    
    Stores all professional information collected during onboarding
    via one of three methods:
        1. Manual entry (CRUD API)
        2. Resume extraction (AI parsing)
        3. Voice registration (Conversational AI)
    
    Attributes:
        Contact: email, phone
        Professional: specialization, experience, registration, fee
        Expertise: languages (JSON array)
        Locations: practice_locations (JSON array of objects)
        Meta: onboarding_source, timestamps, raw_extraction_data
        
    Relationships:
        qualifications: One-to-many with Qualification (cascade delete)
    """

    __tablename__ = "doctors"

    # ==========================================================================
    # PRIMARY KEY
    # ==========================================================================
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    # ==========================================================================
    # CONTACT DETAILS
    # ==========================================================================
    email: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,   # NULL for phone-only signups; filled during onboarding
        index=True,
    )

    phone: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=True,
        comment="Phone number as string to support international formats with + prefix",
    )

    # ==========================================================================
    # AUTHORIZATION
    # ==========================================================================
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="user",
        server_default="user",
        index=True,
        comment="User role: admin, operation, or user (default)",
    )

    onboarding_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
        comment="Onboarding status: pending, submitted, verified, rejected",
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
    primary_specialization: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Primary medical specialty (Cardiology, Neurology, etc.)",
    )
    years_of_experience: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    consultation_fee: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Consultation fee amount",
    )
    consultation_currency: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        default="INR",
        comment="Currency code for consultation fee",
    )
    medical_registration_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Medical council registration/license number",
    )
    medical_council: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Name of the medical council that issued the registration (e.g. Maharashtra Medical Council)",
    )
    registration_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Year of medical registration",
    )
    registration_authority: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Issuing medical council or authority",
    )
    conditions_treated: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        comment="List of conditions commonly treated",
    )

    # ==========================================================================
    # EXPERTISE (JSON ARRAYS)
    # ==========================================================================

    languages: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        comment="Languages spoken",
    )

    # ==========================================================================
    # PRACTICE LOCATIONS (JSON ARRAY OF OBJECTS)
    # ==========================================================================

    practice_locations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        comment="Practice locations: [{hospital_name, address, city, state, phone_number, consultation_fee, consultation_type, weekly_schedule}]",
    )

    # ==========================================================================
    # ONBOARDING METADATA
    # ==========================================================================

    onboarding_source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="How doctor was onboarded: manual, resume, voice",
    )

    resume_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="URL to uploaded resume file",
    )

    # Media & documents (URL storage)
    profile_photo: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Profile photo URL",
    )

    verbal_intro_file: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Verbal introduction file URL",
    )

    professional_documents: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        comment="Professional document URLs as JSON array",
    )

    achievement_images: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        comment="Achievement image URLs as JSON array",
    )

    external_links: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        comment="External links as JSON array",
    )

    raw_extraction_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Raw AI extraction output for debugging/audit",
    )

    # ==========================================================================
    # TIMESTAMPS
    # ==========================================================================
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )

    # ==========================================================================
    # TABLE CONFIGURATION
    # ==========================================================================
    __table_args__ = (
        # Composite index for common filters
        Index("ix_doctors_spec_exp", "primary_specialization", "years_of_experience"),
    )

    # ==========================================================================
    # RELATIONSHIPS
    # ==========================================================================
    # One-to-one with User (optional - a user may be linked to this doctor)
    user: Mapped[User | None] = relationship(
        "User",
        back_populates="doctor",
        uselist=False,
        lazy="selectin",
    )

    # ==========================================================================
    # METHODS
    # ==========================================================================
    def __repr__(self) -> str:
        return f"<Doctor(id={self.id}, email='{self.email}')>"

    @property
    def language_names(self) -> list[str]:
        """Get language names."""
        return self.languages

    # Property mappings for schema compatibility
    @property
    def phone_number(self) -> str | None:
        """Map phone field to phone_number for response schema."""
        return str(self.phone) if self.phone else None

    @property
    def awards_recognition(self) -> list[str]:
        """Map professional_memberships to awards_recognition for response schema."""
        return self.professional_memberships

    @property
    def memberships(self) -> list[str]:
        """Map professional_memberships field to memberships for response schema."""
        return self.professional_memberships

