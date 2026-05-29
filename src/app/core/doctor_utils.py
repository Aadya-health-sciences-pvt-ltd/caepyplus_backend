"""Shared doctor-related helper utilities.

Provides helpers that are reused across multiple endpoint modules.
Placing them here avoids cross-module imports between sibling endpoint files,
which violates the principle that endpoint modules must not import from each other.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime

from ..models.doctor import Doctor
from ..schemas.onboarding import DoctorIdentityResponse

# Synthetic emails written when doctor_identity is bootstrapped without a real address.
PLACEHOLDER_IDENTITY_EMAIL_RE = re.compile(
    r"^placeholder_\d+@caepy\.com$",
    re.IGNORECASE,
)
DISPLACED_IDENTITY_EMAIL_RE = re.compile(
    r"^_displaced_[a-f0-9]+@placeholder$",
    re.IGNORECASE,
)
DOCTOR_PLACEHOLDER_NAME_RE = re.compile(r"^Doctor \d+$", re.IGNORECASE)
UNKNOWN_IDENTITY_PHONE_RE = re.compile(r"^UNKNOWN_\d+$", re.IGNORECASE)


def is_synthetic_identity_email(email: str | None) -> bool:
    """True for bootstrap / collision placeholder emails, not real user addresses."""
    if not email or not str(email).strip():
        return True
    normalized = str(email).strip()
    return bool(
        PLACEHOLDER_IDENTITY_EMAIL_RE.match(normalized)
        or DISPLACED_IDENTITY_EMAIL_RE.match(normalized)
    )


def is_synthetic_identity_full_name(
    full_name: str | None,
    *,
    doctor_id: int | None = None,
) -> bool:
    """True for bootstrap placeholders like ``Doctor {id}``, not real names."""
    if not full_name or not str(full_name).strip():
        return True
    name = str(full_name).strip()
    if doctor_id is not None and name == f"Doctor {doctor_id}":
        return True
    return bool(DOCTOR_PLACEHOLDER_NAME_RE.match(name))


def is_synthetic_identity_phone(
    phone_number: str | None,
    *,
    doctor_id: int | None = None,
) -> bool:
    """True for bootstrap placeholders like ``UNKNOWN_{id}``, not real numbers."""
    if not phone_number or not str(phone_number).strip():
        return True
    phone = str(phone_number).strip()
    if doctor_id is not None and phone == f"UNKNOWN_{doctor_id}":
        return True
    return bool(UNKNOWN_IDENTITY_PHONE_RE.match(phone))


def resolve_display_email(
    identity_email: str | None,
    doctor_email: str | None,
) -> str:
    """Prefer a real identity email; fall back to doctors.email when identity is synthetic."""
    identity = (identity_email or "").strip()
    doctor = (doctor_email or "").strip()
    if identity and not is_synthetic_identity_email(identity):
        return identity
    if doctor and not doctor.lower().startswith("pending_"):
        return doctor
    return identity or doctor or ""


def resolve_display_full_name(
    identity_full_name: str | None,
    doctor_full_name: str | None,
    *,
    doctor_id: int | None = None,
) -> str:
    """Prefer a real doctors-row name; fall back when identity is synthetic."""
    doctor = (doctor_full_name or "").strip()
    identity = (identity_full_name or "").strip()
    if doctor and not is_synthetic_identity_full_name(doctor, doctor_id=doctor_id):
        return doctor
    if identity and not is_synthetic_identity_full_name(identity, doctor_id=doctor_id):
        return identity
    return doctor or identity or ""


def resolve_display_phone(
    identity_phone: str | None,
    doctor_phone: str | None,
    *,
    doctor_id: int | None = None,
) -> str:
    """Prefer a real doctors-row phone; fall back when identity is synthetic."""
    doctor = (doctor_phone or "").strip()
    identity = (identity_phone or "").strip()
    if doctor and not is_synthetic_identity_phone(doctor, doctor_id=doctor_id):
        return doctor
    if identity and not is_synthetic_identity_phone(identity, doctor_id=doctor_id):
        return identity
    return doctor or identity or ""


def synthesise_identity(doctor: Doctor) -> DoctorIdentityResponse:
    """Build a DoctorIdentityResponse from a bare doctors row.

    When a doctor exists only in the doctors table (e.g. created via OTP)
    and has no matching doctor_identity row, this helper synthesises an
    equivalent response so admin endpoints return consistent data.
    """
    return DoctorIdentityResponse(
        id=str(doctor.id),
        doctor_id=doctor.id,
        full_name=doctor.full_name or "",
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
