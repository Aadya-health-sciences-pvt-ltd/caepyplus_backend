"""
Lead Doctor Response Schemas.

Pydantic models for the lead_doctors API endpoints.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LeadDoctorResponse(BaseModel):
    """Response schema for a single lead doctor record."""

    id: int
    city: str | None = None
    speciality: str | None = None
    doctor_name: str | None = None
    qualification: str | None = None
    specialization: str | None = None
    experience: str | None = None
    fee: str | None = None
    location: str | None = None
    hospital_name: str | None = None
    hospital_address: str | None = None
    awards: str | None = None
    memberships: str | None = None
    registrations: str | None = None
    services: str | None = None
    profile_url: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
