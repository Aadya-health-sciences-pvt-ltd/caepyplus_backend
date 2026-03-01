"""Shared doctor-related helper utilities.

Provides helpers that are reused across multiple endpoint modules.
Placing them here avoids cross-module imports between sibling endpoint files,
which violates the principle that endpoint modules must not import from each other.
"""
from __future__ import annotations

from datetime import UTC, datetime

from ..models.doctor import Doctor
from ..schemas.onboarding import DoctorIdentityResponse


def synthesise_identity(doctor: Doctor) -> DoctorIdentityResponse:
    """Build a DoctorIdentityResponse from a bare doctors row.

    When a doctor exists only in the doctors table (e.g. created via OTP)
    and has no matching doctor_identity row, this helper synthesises an
    equivalent response so admin endpoints return consistent data.
    """
    return DoctorIdentityResponse(
        id=str(doctor.id),
        doctor_id=doctor.id,
        title=doctor.title,
        first_name=doctor.first_name or "",
        last_name=doctor.last_name or "",
        email=doctor.email or "",
        phone_number=doctor.phone or "",
        onboarding_status=(doctor.onboarding_status or "pending").lower(),
        status_updated_at=None,
        status_updated_by=None,
        rejection_reason=None,
        verified_at=None,
        is_active=True,
        registered_at=doctor.created_at or datetime.now(UTC),
        created_at=doctor.created_at or datetime.now(UTC),
        updated_at=doctor.updated_at or doctor.created_at or datetime.now(UTC),
        deleted_at=None,
    )
