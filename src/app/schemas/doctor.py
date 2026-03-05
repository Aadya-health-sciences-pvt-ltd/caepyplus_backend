"""
Doctor Domain Schemas.

Pydantic schemas for request/response validation and serialization.
Follows strict separation between DTOs and domain models.
"""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ============================================
# Enumerations
# ============================================

class OnboardingSource(str, Enum):
    """How the doctor was onboarded."""
    RESUME = "resume"
    VOICE = "voice"
    MANUAL = "manual"

# ============================================
# Nested Schemas (Value Objects)
# ============================================

class QualificationBase(BaseModel):
    """Base schema for educational qualifications."""

    degree: str | None = Field(default=None, description="Degree name (e.g., MBBS, MD)")
    institution: str | None = Field(default=None, description="Institution name")
    year: int | None = Field(default=None, ge=1900, le=2100, description="Completion year")

class QualificationCreate(QualificationBase):
    """Schema for creating a qualification."""
    degree: str = Field(min_length=1, description="Degree name is required")

class QualificationResponse(BaseModel):
    """Schema for qualification in responses."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int | None = None  # Optional since qualifications are stored as JSON, not separate table rows
    degree: str | None = Field(default=None)
    institution: str | None = Field(default=None)
    year: int | None = Field(default=None)

class PracticeLocationBase(BaseModel):
    """Base schema for practice locations."""

    hospital_name: str | None = Field(default=None, description="Hospital or clinic name")
    address: str | None = Field(default=None, description="Full address")
    city: str | None = Field(default=None, description="City")
    state: str | None = Field(default=None, description="State or province")
    phone_number: str | None = Field(default=None, description="Contact phone number")
    consultation_fee: float | None = Field(default=None, ge=0, description="Consultation fee")
    consultation_type: str | None = Field(default=None, description="Type of consultation (In-person, Online, etc.)")
    weekly_schedule: str | None = Field(default=None, description="Weekly schedule or timings")

# ============================================
# Doctor Schemas
# ============================================

class DoctorBase(BaseModel):
    """Base schema with common doctor fields."""


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
    email: EmailStr = Field(description="Email address (must be unique)")
    phone_number: str | None = Field(default=None, max_length=30, description="Phone number")
    primary_specialization: str = Field(
        min_length=1,
        max_length=200,
        description="Primary medical specialization"
    )
    years_of_experience: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Years of practice"
    )
    consultation_fee: float | None = Field(
        default=None,
        ge=0,
        description="Consultation fee"
    )
    medical_registration_number: str = Field(
        min_length=1,
        max_length=100,
        description="Medical registration/license number",
    )
    medical_council: str | None = Field(
        default=None,
        max_length=200,
        description="Name of the medical council that issued the registration (e.g. Maharashtra Medical Council)",
    )
    registration_year: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Year of medical registration",
    )
    registration_authority: str | None = Field(
        default=None,
        max_length=200,
        description="Issuing medical council or authority",
    )
    languages: list[str] = Field(default_factory=list, description="Languages spoken")
    conditions_treated: list[str] = Field(default_factory=list, description="Conditions commonly treated")
    awards_recognition: list[str] = Field(default_factory=list, description="Awards and recognition")
    memberships: list[str] = Field(default_factory=list, description="Professional memberships")
    profile_photo: str | None = Field(default=None, description="Profile photo URL")
    verbal_intro_file: str | None = Field(default=None, description="Verbal introduction file URL")
    professional_documents: list[str] = Field(default_factory=list, description="Professional document URLs")
    achievement_images: list[str] = Field(default_factory=list, description="Achievement image URLs")
    external_links: list[str] = Field(default_factory=list, description="External profile links")
    practice_locations: list[PracticeLocationBase] = Field(
        default_factory=list,
        description="Practice locations"
    )

class DoctorCreate(DoctorBase):
    """
    Schema for creating a new doctor.
    
    Used in POST /api/v1/doctors endpoint.
    """

    onboarding_source: OnboardingSource | None = Field(
        default=None,
        description="Source of onboarding data"
    )
    resume_url: str | None = Field(default=None, description="URL to uploaded resume")
    raw_extraction_data: dict[str, Any] | None = Field(
        default=None,
        description="Raw AI extraction output"
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalize email to lowercase."""
        return v.lower().strip()

class DoctorUpdate(BaseModel):
    """
    Schema for updating a doctor.
    
    All fields are optional - only provided fields are updated.
    """

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

    # Existing fields (legacy/compatibility)
    email: EmailStr | None = None
    phone_number: str | None = None
    primary_specialization: str | None = Field(default=None, min_length=1, max_length=200)
    years_of_experience: int | None = Field(default=None, ge=0, le=100)
    consultation_fee: float | None = Field(default=None, ge=0)
    medical_registration_number: str | None = Field(default=None, min_length=1, max_length=100)
    medical_council: str | None = Field(default=None, max_length=200, description="Name of the issuing medical council")
    registration_year: int | None = Field(default=None, ge=1900, le=2100)
    registration_authority: str | None = None
    languages: list[str] | None = None
    conditions_treated: list[str] | None = None
    awards_recognition: list[str] | None = None
    memberships: list[str] | None = None
    profile_photo: str | None = None
    verbal_intro_file: str | None = None
    professional_documents: list[str] | None = None
    achievement_images: list[str] | None = None
    external_links: list[str] | None = None
    practice_locations: list[PracticeLocationBase] | None = None

class DoctorResponse(BaseModel):
    """
    Schema for doctor in API responses.
    
    Includes all fields plus database-generated fields.
    """


    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    email: str | None = None
    phone_number: str | None = Field(default=None, validation_alias="phone")
    primary_specialization: str | None = None
    years_of_experience: int | None = None
    consultation_fee: float | None = None
    consultation_currency: str | None = None
    medical_registration_number: str | None = None
    medical_council: str | None = None
    registration_year: int | None = None
    registration_authority: str | None = None
    languages: list[str] = Field(default_factory=list)
    conditions_treated: list[str] = Field(default_factory=list)
    awards_recognition: list[str] = Field(default_factory=list)
    memberships: list[str] = Field(default_factory=list)
    profile_photo: str | None = None
    verbal_intro_file: str | None = None
    professional_documents: list[str] = Field(default_factory=list)
    achievement_images: list[str] = Field(default_factory=list)
    external_links: list[str] = Field(default_factory=list)
    practice_locations: list[PracticeLocationBase] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)  # Simple string list (e.g., ["MBBS", "MD Cardiology"])
    onboarding_source: str | None = None
    role: str = "user"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Block 1: Professional Identity
    full_name: str | None = None
    specialty: str | None = None
    primary_practice_location: str | None = None
    centres_of_practice: list[str] = Field(default_factory=list)
    years_of_clinical_experience: int | None = None
    years_post_specialisation: int | None = None

    # Block 2: Credentials & Trust Markers
    year_of_mbbs: int | None = None
    year_of_specialisation: int | None = None
    fellowships: list[str] = Field(default_factory=list)
    professional_memberships: list[str] = Field(default_factory=list)
    awards_academic_honours: list[str] = Field(default_factory=list)

    # Block 3: Clinical Focus & Expertise
    areas_of_clinical_interest: list[str] = Field(default_factory=list)
    practice_segments: str | None = None
    conditions_commonly_treated: list[str] = Field(default_factory=list)
    conditions_known_for: list[str] = Field(default_factory=list)
    conditions_want_to_treat_more: list[str] = Field(default_factory=list)

    # Block 4: The Human Side
    training_experience: list[str] = Field(default_factory=list)
    motivation_in_practice: list[str] = Field(default_factory=list)
    unwinding_after_work: list[str] = Field(default_factory=list)
    recognition_identity: list[str] = Field(default_factory=list)
    quality_time_interests: list[str] = Field(default_factory=list)
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
    content_seeds: list[dict[str, Any]] = Field(default_factory=list)

class DoctorSummary(BaseModel):
    """
    Minimal doctor information for list views.
    
    Used in list endpoints to reduce payload size.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None = None
    primary_specialization: str | None = None
    years_of_experience: int | None = None
    created_at: datetime

# ============================================
# Resume Extraction Schemas
# ============================================

class PersonalDetails(BaseModel):
    """Extracted personal details from resume."""
    email: str | None = None
    phone: str | None = None

class ProfessionalInformation(BaseModel):
    """Extracted professional information from resume."""
    primary_specialization: str | None = None
    years_of_experience: int | None = None
    conditions_treated: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

class Registration(BaseModel):
    """Extracted registration information from resume."""
    medical_registration_number: str | None = None
    medical_council: str | None = None
    registration_year: int | None = None
    registration_authority: str | None = None

class Achievements(BaseModel):
    """Extracted achievements from resume."""
    awards_recognition: list[str] = Field(default_factory=list)
    memberships: list[str] = Field(default_factory=list)

class Media(BaseModel):
    """Extracted media and documents from resume."""
    verbal_intro_file: str | None = None
    professional_documents: list[str] = Field(default_factory=list)
    achievement_images: list[str] = Field(default_factory=list)
    external_links: list[str] = Field(default_factory=list)

class ResumeExtractedData(BaseModel):
    """
    Complete data extracted from resume by AI.
    
    This schema matches the AI extraction output format.
    """

    personal_details: PersonalDetails = Field(default_factory=PersonalDetails)
    professional_information: ProfessionalInformation = Field(default_factory=ProfessionalInformation)
    registration: Registration = Field(default_factory=Registration)
    qualifications: list[QualificationBase] = Field(default_factory=list)
    achievements: Achievements = Field(default_factory=Achievements)
    media: Media = Field(default_factory=Media)
    practice_locations: list[PracticeLocationBase] = Field(default_factory=list)

    def to_doctor_create(self, source: OnboardingSource = OnboardingSource.RESUME) -> DoctorCreate:
        """Convert extracted data to DoctorCreate schema."""
        # Convert qualifications from structured format to strings
        qualification_strings = [
            f"{q.degree} - {q.institution} ({q.year})" if q.institution and q.year
            else f"{q.degree} - {q.institution}" if q.institution
            else f"{q.degree} ({q.year})" if q.year
            else q.degree
            for q in self.qualifications
            if q.degree
        ]

        return DoctorCreate(
            email=self.personal_details.email or "",
            phone_number=self.personal_details.phone,
            primary_specialization=self.professional_information.primary_specialization or "",
            years_of_experience=self.professional_information.years_of_experience,
            consultation_fee=None,
            medical_registration_number=self.registration.medical_registration_number or "",
            medical_council=self.registration.medical_council,
            registration_year=self.registration.registration_year,
            registration_authority=self.registration.registration_authority,
            languages=self.professional_information.languages,
            conditions_treated=self.professional_information.conditions_treated,
            awards_recognition=self.achievements.awards_recognition,
            memberships=self.achievements.memberships,
            verbal_intro_file=self.media.verbal_intro_file,
            professional_documents=self.media.professional_documents,
            achievement_images=self.media.achievement_images,
            external_links=self.media.external_links,
            practice_locations=self.practice_locations,
            qualifications=qualification_strings,
            onboarding_source=source,
            raw_extraction_data=self.model_dump(),
        )

# ============================================
# Extraction Response Schemas
# ============================================

class ExtractionResponse(BaseModel):
    """Response from resume extraction endpoint."""

    success: bool = True
    message: str
    data: ResumeExtractedData | None = None
    processing_time_ms: float | None = None

class ProfileContentRequest(DoctorBase):
    """Request payload for generating profile content from onboarding fields."""

    # Optional: Specify doctor identifier for session tracking
    doctor_identifier: str | None = Field(
        default=None,
        description="Unique identifier for the doctor (email or ID) for variant session tracking"
    )

    # Optional: Specify which sections to regenerate (if not provided, all sections generated)
    sections: list[str] | None = Field(
        default=None,
        description="Specific sections to regenerate: professional_overview, about_me, professional_tagline"
    )


class ProfileContentResponse(BaseModel):
    """Generated profile content fields for a doctor."""

    professional_overview: str | None = None
    about_me: str | None = None
    professional_tagline: str | None = None

    # Metadata about variants used (for debugging/tracking)
    variants_used: dict[str, int] | None = Field(
        default=None,
        description="Map of section name to variant index used (1-indexed for display)"
    )


class ProfileSessionStatsResponse(BaseModel):
    """Response for prompt session statistics."""

    doctor_identifier: str
    sections: dict[str, dict[str, Any]]
    total_regenerations: int = 0

