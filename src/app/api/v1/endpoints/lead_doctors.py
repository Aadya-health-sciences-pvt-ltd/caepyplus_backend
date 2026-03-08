"""
Lead Doctors API Endpoints.

Admin/Operation-only endpoint for listing lead doctor data with
pagination and column filtering.
"""
from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Depends, Query

from ....core.rbac import AdminOrOperationUser
from ....core.responses import PaginatedResponse, PaginationMeta
from ....db.session import DbSession
from ....repositories.lead_doctor_repository import LeadDoctorRepository
from ....schemas.lead_doctor import LeadDoctorResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/lead-doctors", tags=["Lead Doctors"])


def _get_repo(db: DbSession) -> LeadDoctorRepository:
    return LeadDoctorRepository(db)


@router.get(
    "",
    response_model=PaginatedResponse[LeadDoctorResponse],
    summary="List lead doctors (Admin/Operation only)",
    description=(
        "Paginated listing of lead doctor data imported from external sources. "
        "Supports filtering by city, speciality, specialization, doctor name, "
        "location, and hospital name. All text filters are case-insensitive "
        "partial matches."
    ),
)
async def list_lead_doctors(
    current_user: AdminOrOperationUser,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    city: str | None = Query(None, description="Filter by city (partial match)"),
    speciality: str | None = Query(None, description="Filter by speciality (partial match)"),
    specialization: str | None = Query(None, description="Filter by specialization (partial match)"),
    doctor_name: str | None = Query(None, description="Filter by doctor name (partial match)"),
    location: str | None = Query(None, description="Filter by location (partial match)"),
    hospital_name: str | None = Query(None, description="Filter by hospital name (partial match)"),
) -> PaginatedResponse[LeadDoctorResponse]:
    """List all lead doctors with pagination and optional column filters.

    Requires Admin or Operation role.
    """
    repo = LeadDoctorRepository(db)

    filter_kwargs = dict(
        city=city,
        speciality=speciality,
        specialization=specialization,
        doctor_name=doctor_name,
        location=location,
        hospital_name=hospital_name,
    )

    # Run data + count queries concurrently for performance
    leads, total = await asyncio.gather(
        repo.get_all(page=page, page_size=page_size, **filter_kwargs),
        repo.count(**filter_kwargs),
    )

    return PaginatedResponse(
        message=f"Found {total} lead doctor(s)",
        data=[LeadDoctorResponse.model_validate(lead) for lead in leads],
        pagination=PaginationMeta.from_total(total, page, page_size),
    )
