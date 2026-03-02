"""
Doctor Repository.

Data access layer for doctor entities using SQLAlchemy 2.0 async patterns.
Follows the Repository pattern for clean separation of concerns.
"""
from collections.abc import Sequence

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import DoctorAlreadyExistsError, DoctorNotFoundError
from ..models.doctor import Doctor
from ..schemas.doctor import DoctorCreate, DoctorUpdate, PracticeLocationBase

logger = structlog.get_logger(__name__)


class DoctorRepository:
    """
    Repository for Doctor entity database operations.
    
    Provides CRUD operations and query methods following
    SQLAlchemy 2.0 async patterns.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with database session."""
        self.session = session

    async def create(self, data: DoctorCreate) -> Doctor:
        """
        Create a new doctor record.
        
        Args:
            data: Validated doctor creation data
            
        Returns:
            Created doctor entity
            
        Raises:
            DoctorAlreadyExistsError: If email already exists
        """
        # Normalize email to lowercase before any lookup or persist.
        # get_by_email() lowercases on every lookup — persisting in mixed-case
        # would cause a unique-constraint miss on a subsequent login attempt.
        normalized_email = data.email.lower() if data.email else data.email
        existing = await self.get_by_email(normalized_email) if normalized_email else None
        if existing:
            raise DoctorAlreadyExistsError(normalized_email)

        # Create doctor entity with qualifications as JSON
        doctor = Doctor(
            # Block 1
            full_name=data.full_name,
            specialty=data.specialty,
            primary_practice_location=data.primary_practice_location,
            centres_of_practice=data.centres_of_practice or [],
            years_of_clinical_experience=data.years_of_clinical_experience,
            years_post_specialisation=data.years_post_specialisation,
            # Block 2
            year_of_mbbs=data.year_of_mbbs,
            year_of_specialisation=data.year_of_specialisation,
            fellowships=data.fellowships or [],
            qualifications=data.qualifications or [],
            professional_memberships=data.professional_memberships or [],
            awards_academic_honours=data.awards_academic_honours or [],
            # Block 3
            areas_of_clinical_interest=data.areas_of_clinical_interest or [],
            practice_segments=data.practice_segments,
            conditions_commonly_treated=data.conditions_commonly_treated or [],
            conditions_known_for=data.conditions_known_for or [],
            conditions_want_to_treat_more=data.conditions_want_to_treat_more or [],
            # Block 4
            training_experience=data.training_experience or [],
            motivation_in_practice=data.motivation_in_practice or [],
            unwinding_after_work=data.unwinding_after_work or [],
            recognition_identity=data.recognition_identity or [],
            quality_time_interests=data.quality_time_interests or [],
            quality_time_interests_text=data.quality_time_interests_text,
            professional_achievement=data.professional_achievement,
            personal_achievement=data.personal_achievement,
            professional_aspiration=data.professional_aspiration,
            personal_aspiration=data.personal_aspiration,
            # Block 5
            what_patients_value_most=data.what_patients_value_most,
            approach_to_care=data.approach_to_care,
            availability_philosophy=data.availability_philosophy,
            # Block 6
            content_seeds=data.content_seeds or [],
            # Existing fields
            email=normalized_email,
            phone=data.phone_number,
            primary_specialization=data.primary_specialization,
            years_of_experience=data.years_of_experience,
            consultation_fee=data.consultation_fee,
            medical_registration_number=data.medical_registration_number,
            medical_council=data.medical_council,
            languages=data.languages,
            achievements=data.awards_recognition,
            practice_locations=[loc.model_dump() for loc in data.practice_locations],
            onboarding_source=data.onboarding_source.value if data.onboarding_source else None,
            resume_url=data.resume_url,
            raw_extraction_data=data.raw_extraction_data,
        )

        self.session.add(doctor)
        await self.session.commit()
        await self.session.refresh(doctor)

        logger.info("Created doctor", doctor_id=doctor.id, email=doctor.email)

        return doctor

    async def get_by_id(self, doctor_id: int) -> Doctor | None:
        """Get doctor by ID."""
        query = select(Doctor).where(Doctor.id == doctor_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(self, doctor_id: int) -> Doctor:
        """Get doctor by ID or raise NotFoundError."""
        doctor = await self.get_by_id(doctor_id)
        if not doctor:
            raise DoctorNotFoundError(doctor_id=doctor_id)
        return doctor

    async def get_by_email(self, email: str) -> Doctor | None:
        """Get doctor by email address."""
        query = select(Doctor).where(Doctor.email == email.lower())
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_phone_number(self, phone_number: str) -> Doctor | None:
        """Get doctor by phone number (stored as string with +91 prefix)."""
        # Normalize: ensure it has +91 prefix (same as create_from_phone)
        normalized = phone_number.strip()
        if not normalized:
            return None

        # Extract only digits
        digits_only = ''.join(c for c in normalized if c.isdigit())

        # Handle different input formats:
        # - "9988776655" -> "+919988776655"
        # - "919988776655" -> "+919988776655"
        # - "+919988776655" -> "+919988776655"
        if digits_only.startswith('91') and len(digits_only) == 12:
            # Already has country code
            normalized = '+' + digits_only
        else:
            # Add +91 for Indian numbers
            normalized = '+91' + digits_only

        query = select(Doctor).where(Doctor.phone == normalized)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_registration_number(self, reg_number: str) -> Doctor | None:
        """Get doctor by medical registration number."""
        query = select(Doctor).where(Doctor.medical_registration_number == reg_number)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        specialization: str | None = None,
    ) -> Sequence[Doctor]:
        """
        Get all doctors with pagination and optional filtering.
        
        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            specialization: Filter by specialization (optional)
            
        Returns:
            List of doctor entities
        """
        query = select(Doctor).order_by(Doctor.created_at.desc())

        # Apply filters BEFORE offset/limit for correct pagination
        if specialization:
            query = query.where(
                Doctor.primary_specialization.ilike(f"%{specialization}%")
            )

        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def count(self, specialization: str | None = None) -> int:
        """Count total doctors with optional filtering."""
        query = select(func.count(Doctor.id))

        if specialization:
            query = query.where(
                Doctor.primary_specialization.ilike(f"%{specialization}%")
            )

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(self, doctor_id: int, data: DoctorUpdate) -> Doctor:
        """
        Update an existing doctor record.
        
        Args:
            doctor_id: ID of doctor to update
            data: Update data (only non-None fields are updated)
            
        Returns:
            Updated doctor entity
            
        Raises:
            DoctorNotFoundError: If doctor doesn't exist
        """
        doctor = await self.get_by_id_or_raise(doctor_id)

        # Update only provided fields
        update_data = data.model_dump(exclude_unset=True, exclude_none=True)

        # Handle nested objects - practice_locations
        if "practice_locations" in update_data:
            update_data["practice_locations"] = [
                loc.model_dump() if isinstance(loc, PracticeLocationBase) else loc
                for loc in update_data["practice_locations"]
            ]

        # Qualifications are stored as list[str] - no conversion needed

        # Map schema field names to model field names
        field_mapping = {
            "awards_recognition": "achievements",
            "memberships": "professional_memberships",
            "phone_number": "phone",
        }

        # Update fields
        for field, value in update_data.items():
            model_field = field_mapping.get(field, field)
            if hasattr(doctor, model_field):
                setattr(doctor, model_field, value)

        await self.session.commit()
        await self.session.refresh(doctor)

        logger.info("Updated doctor", doctor_id=doctor_id)

        return doctor

    async def create_from_phone(
        self,
        phone_number: str,
        role: str = "user",
    ) -> Doctor:
        """
        Create a new doctor record from phone number only.
        
        Used during OTP verification when a new user signs up.
        Creates a minimal record with phone number and default role.
        The doctor can complete their profile later.
        
        Args:
            phone_number: Verified phone number (will be normalized)
            role: User role (admin, operational, user). Defaults to 'user'.
            
        Returns:
            Created doctor entity with ID
        """
        # Normalize phone number to include + prefix
        normalized_phone = phone_number.strip()
        if not normalized_phone.startswith('+'):
            # Add +91 for Indian numbers
            normalized_phone = '+91' + ''.join(c for c in normalized_phone if c.isdigit())

        # Create minimal doctor record.
        # email stays NULL — fake placeholders block future real email updates
        # and pollute get_by_email().
        doctor = Doctor(
            phone=normalized_phone,
            email=None,      # Provided during onboarding
            role=role,
        )

        self.session.add(doctor)
        await self.session.commit()
        await self.session.refresh(doctor)

        logger.info("Created doctor from phone", doctor_id=doctor.id, phone=normalized_phone)

        return doctor

    async def create_from_email(
        self,
        email: str,
        name: str = "",
        role: str = "user",
    ) -> Doctor:
        """
        Create a new doctor record from email address (Google Sign-In).
        
        Used during Google Sign-In when a new user signs up.
        Creates a minimal record with email and name.
        The doctor can complete their profile later during onboarding.
        
        Args:
            email: Verified email address from Google
            name: Display name from Google account
            role: User role. Defaults to 'user'.
            
        Returns:
            Created doctor entity with ID
        """
        doctor = Doctor(
            email=email.lower(),
            phone=None,  # Provided during onboarding (Google users may not have one)
            role=role,
        )

        self.session.add(doctor)
        await self.session.commit()
        await self.session.refresh(doctor)

        logger.info("Created doctor from email", doctor_id=doctor.id, email=email)

        return doctor

    async def delete(self, doctor_id: int) -> bool:
        """
        Delete a doctor record.
        
        Args:
            doctor_id: ID of doctor to delete
            
        Returns:
            True if deleted, False if not found
        """
        doctor = await self.get_by_id(doctor_id)
        if not doctor:
            return False

        await self.session.delete(doctor)
        await self.session.commit()

        logger.info("Deleted doctor", doctor_id=doctor_id)

        return True

    async def delete_or_raise(self, doctor_id: int) -> None:
        """Delete a doctor or raise NotFoundError."""
        deleted = await self.delete(doctor_id)
        if not deleted:
            raise DoctorNotFoundError(doctor_id=doctor_id)

