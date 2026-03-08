"""
Lead Doctor Repository.

Data access layer for lead_doctors table using SQLAlchemy 2.0 async patterns.
"""
from __future__ import annotations

from collections.abc import Sequence

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.lead_doctor import LeadDoctor

logger = structlog.get_logger(__name__)


class LeadDoctorRepository:
    """Repository for LeadDoctor entity database operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with database session."""
        self.session = session

    async def get_all(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        city: str | None = None,
        speciality: str | None = None,
        specialization: str | None = None,
        doctor_name: str | None = None,
        location: str | None = None,
        hospital_name: str | None = None,
    ) -> Sequence[LeadDoctor]:
        """
        Get lead doctors with pagination and optional filtering.

        All text filters use case-insensitive partial matching (ILIKE).

        Args:
            page: Page number (1-indexed).
            page_size: Number of records per page.
            city: Filter by city.
            speciality: Filter by speciality.
            specialization: Filter by specialization.
            doctor_name: Filter by doctor name.
            location: Filter by location.
            hospital_name: Filter by hospital name.

        Returns:
            List of LeadDoctor entities for the requested page.
        """
        query = select(LeadDoctor).order_by(LeadDoctor.id.asc())

        # Apply filters BEFORE offset/limit for correct pagination
        if city:
            query = query.where(LeadDoctor.city.ilike(f"%{city}%"))
        if speciality:
            query = query.where(LeadDoctor.speciality.ilike(f"%{speciality}%"))
        if specialization:
            query = query.where(LeadDoctor.specialization.ilike(f"%{specialization}%"))
        if doctor_name:
            query = query.where(LeadDoctor.doctor_name.ilike(f"%{doctor_name}%"))
        if location:
            query = query.where(LeadDoctor.location.ilike(f"%{location}%"))
        if hospital_name:
            query = query.where(LeadDoctor.hospital_name.ilike(f"%{hospital_name}%"))

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def count(
        self,
        *,
        city: str | None = None,
        speciality: str | None = None,
        specialization: str | None = None,
        doctor_name: str | None = None,
        location: str | None = None,
        hospital_name: str | None = None,
    ) -> int:
        """Count total lead doctors with optional filtering.

        Mirrors the same filters as ``get_all`` for accurate pagination.
        """
        query = select(func.count(LeadDoctor.id))

        if city:
            query = query.where(LeadDoctor.city.ilike(f"%{city}%"))
        if speciality:
            query = query.where(LeadDoctor.speciality.ilike(f"%{speciality}%"))
        if specialization:
            query = query.where(LeadDoctor.specialization.ilike(f"%{specialization}%"))
        if doctor_name:
            query = query.where(LeadDoctor.doctor_name.ilike(f"%{doctor_name}%"))
        if location:
            query = query.where(LeadDoctor.location.ilike(f"%{location}%"))
        if hospital_name:
            query = query.where(LeadDoctor.hospital_name.ilike(f"%{hospital_name}%"))

        result = await self.session.execute(query)
        return result.scalar_one()
