"""
Post-persist actions for bulk CSV confirm when ``BULK_VERIFY`` is enabled.

Duplicates the minimal ORM steps from onboarding verify/submit and the LinQMD
create sequence from onboarding-admin sync — without modifying those routes.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.bulk_csv_enrichment import resolve_bulk_linqmd_theme, validate_enriched_bulk_row
from ..models.doctor import Doctor as DoctorModel
from ..models.onboarding import DoctorIdentity, OnboardingStatus
from ..repositories.linqmd_credentials_repository import LinqmdCredentialsRepository
from ..repositories.onboarding_repository import OnboardingRepository
from ..services.linqmd_sync_service import get_linqmd_sync_service


class BulkPostUploadOutcome:
    """Result of bulk verify + optional LinQMD for one row."""

    __slots__ = ("onboarding_status", "warnings")

    def __init__(
        self,
        *,
        onboarding_status: str | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.onboarding_status = onboarding_status
        self.warnings = warnings or []


def _enriched_slice_from_row(row: dict[str, Any]) -> dict[str, Any]:
    enriched = {
        k: v
        for k, v in row.items()
        if not str(k).startswith("_") and k != "phone"
    }
    return enriched


def _raw_slice_for_validation(row: dict[str, Any]) -> dict[str, str]:
    raw: dict[str, str] = {}
    for key in ("year_of_mbbs", "year_of_specialisation", "theme"):
        val = row.get(key)
        if val is not None and val != "":
            raw[key] = str(val)
    return raw


def bulk_verify_readiness_message(row: dict[str, Any], identity: DoctorIdentity | None) -> str | None:
    """Return a human-readable reason if the row is not ready for auto-verify."""
    if identity is None:
        return "Doctor identity record missing; marked as submitted for manual review."

    enriched = _enriched_slice_from_row(row)
    bulk_errors = validate_enriched_bulk_row(0, _raw_slice_for_validation(row), enriched)
    if bulk_errors:
        return bulk_errors[0].error
    return None


async def should_run_bulk_post_upload(
    *,
    is_create: bool,
    doctor: DoctorModel,
    db: AsyncSession,
) -> bool:
    if is_create:
        return True
    if (doctor.onboarding_status or "").lower() == OnboardingStatus.VERIFIED.value:
        return False
    creds_repo = LinqmdCredentialsRepository(db)
    return not await creds_repo.exists_for_doctor(doctor.id)


async def _mark_submitted(
    *,
    db: AsyncSession,
    doctor: DoctorModel,
    identity: DoctorIdentity | None,
    doctor_id: int,
    changed_by: str,
    changed_by_email: str | None,
) -> DoctorIdentity:
    """Mirror ``submit_profile`` status transition (no commit)."""
    repo = OnboardingRepository(db)
    now = datetime.now(UTC)
    previous_status = doctor.onboarding_status

    doctor.onboarding_status = OnboardingStatus.SUBMITTED.value
    doctor.updated_at = now

    if identity is None:
        identity = DoctorIdentity(
            id=str(uuid.uuid4()),
            doctor_id=doctor_id,
            full_name=getattr(doctor, "full_name", None) or "",
            email=doctor.email or "",
            phone_number=doctor.phone or "",
            onboarding_status=OnboardingStatus.SUBMITTED,
        )
        db.add(identity)
        await db.flush()
    else:
        identity.onboarding_status = OnboardingStatus.SUBMITTED
        identity.updated_at = now
        identity.status_updated_at = now
        await repo.sync_identity_from_doctor(
            doctor_id,
            email=doctor.email,
            phone_number=doctor.phone,
            full_name=doctor.full_name,
        )

    await repo.log_status_change(
        doctor_id=doctor_id,
        previous_status=previous_status,
        new_status=OnboardingStatus.SUBMITTED,
        changed_by=changed_by,
        changed_by_email=changed_by_email,
        notes="Bulk CSV: not ready for auto-verify",
    )
    await db.flush()
    return identity


async def _mark_verified(
    *,
    db: AsyncSession,
    doctor: DoctorModel,
    identity: DoctorIdentity | None,
    doctor_id: int,
    changed_by: str,
) -> DoctorIdentity:
    """Mirror ``verify_profile`` status transition (no email, no commit)."""
    repo = OnboardingRepository(db)
    now = datetime.now(UTC)
    previous_status = doctor.onboarding_status

    doctor.onboarding_status = OnboardingStatus.VERIFIED.value
    doctor.updated_at = now

    if identity is None:
        identity = DoctorIdentity(
            id=str(uuid.uuid4()),
            doctor_id=doctor_id,
            full_name=getattr(doctor, "full_name", None) or "",
            email=doctor.email or "",
            phone_number=doctor.phone or "",
            onboarding_status=OnboardingStatus.VERIFIED,
            verified_at=now,
            status_updated_at=now,
            status_updated_by=changed_by,
        )
        db.add(identity)
        await db.flush()
    else:
        identity.onboarding_status = OnboardingStatus.VERIFIED
        identity.verified_at = now
        identity.status_updated_at = now
        identity.status_updated_by = changed_by
        identity.updated_at = now
        await repo.sync_identity_from_doctor(
            doctor_id,
            email=doctor.email,
            phone_number=doctor.phone,
            full_name=doctor.full_name,
        )

    await repo.log_status_change(
        doctor_id=doctor_id,
        previous_status=previous_status,
        new_status=OnboardingStatus.VERIFIED,
        changed_by=changed_by,
        notes="Bulk CSV auto-verify (BULK_VERIFY)",
    )
    await db.flush()
    return identity


async def _create_linqmd_profile(
    *,
    db: AsyncSession,
    doctor_id: int,
    identity: DoctorIdentity,
    theme: str,
) -> str | None:
    """Mirror admin ``sync_doctor_to_linqmd``; return error message or None on success."""
    creds_repo = LinqmdCredentialsRepository(db)
    if await creds_repo.exists_for_doctor(doctor_id):
        return None

    doctor_name = (identity.full_name or "").strip() or f"Doctor {doctor_id}"
    sync_service = get_linqmd_sync_service()
    result = await sync_service.sync_doctor_by_id(doctor_id, db, theme=theme)

    if not result.success:
        detail = result.error_message or "LinQMD sync failed."
        if isinstance(result.linqmd_response, dict):
            linqmd_error = result.linqmd_response.get("error")
            if linqmd_error:
                detail = str(linqmd_error)
        return detail

    linqmd_response = result.linqmd_response if isinstance(result.linqmd_response, dict) else {}
    uid = linqmd_response.get("uid")
    username = linqmd_response.get("Username")
    password = linqmd_response.get("Password")

    if uid is None or str(uid).strip() == "":
        return "LinQMD did not return a user id (uid). Create profile manually in admin."
    if not username or not password:
        return "LinQMD credentials missing from response. Create profile manually in admin."

    try:
        await creds_repo.create(
            doctor_id=doctor_id,
            doctor_name=doctor_name,
            linqmd_user_id=str(uid),
            linqmd_username=str(username),
            linqmd_password=str(password),
        )
        await db.flush()
    except ValueError:
        return "LinQMD profile already exists for this doctor."
    return None


async def apply_bulk_verify_and_linqmd(
    *,
    db: AsyncSession,
    row: dict[str, Any],
    doctor: DoctorModel,
    identity: DoctorIdentity | None,
    is_create: bool,
    changed_by: str,
    changed_by_email: str | None,
) -> BulkPostUploadOutcome:
    """Run auto-verify and LinQMD create for one bulk row (inside caller savepoint)."""
    if not await should_run_bulk_post_upload(is_create=is_create, doctor=doctor, db=db):
        return BulkPostUploadOutcome()

    doctor_id = doctor.id
    readiness = bulk_verify_readiness_message(row, identity)
    if readiness:
        identity = await _mark_submitted(
            db=db,
            doctor=doctor,
            identity=identity,
            doctor_id=doctor_id,
            changed_by=changed_by,
            changed_by_email=changed_by_email,
        )
        return BulkPostUploadOutcome(
            onboarding_status=OnboardingStatus.SUBMITTED.value,
            warnings=[f"Auto-verify skipped: {readiness}"],
        )

    identity = await _mark_verified(
        db=db,
        doctor=doctor,
        identity=identity,
        doctor_id=doctor_id,
        changed_by=changed_by,
    )

    theme = resolve_bulk_linqmd_theme(row)
    linqmd_error = await _create_linqmd_profile(
        db=db,
        doctor_id=doctor_id,
        identity=identity,
        theme=theme,
    )
    if linqmd_error:
        return BulkPostUploadOutcome(
            onboarding_status=OnboardingStatus.VERIFIED.value,
            warnings=[
                f"Profile verified but LinQMD create failed: {linqmd_error} "
                "Use admin LinQMD sync to create the profile manually.",
            ],
        )

    return BulkPostUploadOutcome(onboarding_status=OnboardingStatus.VERIFIED.value)
