"""Tests for bulk CSV theme parsing and BULK_VERIFY post-upload helpers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.endpoints.doctors import _parse_and_validate_csv
from app.core.bulk_csv_enrichment import (
    DEFAULT_BULK_LINQMD_THEME,
    resolve_bulk_linqmd_theme,
    validate_bulk_csv_theme,
)
from app.models.onboarding import OnboardingStatus
from app.services.bulk_csv_post_upload import (
    apply_bulk_verify_and_linqmd,
    bulk_verify_readiness_message,
)
from app.services.linqmd_sync_service import LinQMDSyncResult


def _minimal_valid_csv(extra_header: str = "", extra_value: str = "") -> bytes:
    header = (
        "phone,email,full_name,specialty,city,languages,medical_registration_number,"
        "medical_council,year_of_mbbs"
    )
    if extra_header:
        header += f",{extra_header}"
    row = (
        "9876500099,theme.test@example.com,Dr. Theme Test,Cardiology,Bangalore,"
        "English,REG-THEME-1,Karnataka Medical Council,2012"
    )
    if extra_value:
        row += f",{extra_value}"
    return f"{header}\n{row}\n".encode("utf-8")


def test_validate_bulk_csv_theme_rejects_invalid() -> None:
    err = validate_bulk_csv_theme({"theme": "dp_9"})
    assert err is not None
    assert err.field == "theme"


def test_validate_bulk_csv_theme_accepts_empty() -> None:
    assert validate_bulk_csv_theme({"theme": ""}) is None


def test_resolve_bulk_linqmd_theme_defaults() -> None:
    assert resolve_bulk_linqmd_theme({}) == DEFAULT_BULK_LINQMD_THEME
    assert resolve_bulk_linqmd_theme({"_linqmd_theme": "dp_2"}) == "dp_2"


def test_parse_csv_invalid_theme_fails_validation() -> None:
    _rows, errors = _parse_and_validate_csv(_minimal_valid_csv("theme", "bad_theme"))
    assert any(e.field == "theme" for e in errors)


def test_parse_csv_valid_theme_stored_on_row() -> None:
    rows, errors = _parse_and_validate_csv(_minimal_valid_csv("theme", "dp_1"))
    assert not errors
    assert rows[0]["_linqmd_theme"] == "dp_1"


def test_bulk_verify_readiness_requires_identity() -> None:
    msg = bulk_verify_readiness_message({"full_name": "Dr. X", "email": "a@b.com"}, None)
    assert msg is not None
    assert "identity" in msg.lower()


@pytest.mark.asyncio
async def test_apply_bulk_verify_linqmd_failure_leaves_verified() -> None:
    doctor = MagicMock()
    doctor.id = 42
    doctor.onboarding_status = OnboardingStatus.PENDING.value
    doctor.email = "doc@example.com"
    doctor.phone = "+919876500099"
    doctor.full_name = "Dr. Test"
    doctor.updated_at = None

    identity = MagicMock()
    identity.full_name = "Dr. Test"
    identity.onboarding_status = OnboardingStatus.PENDING

    row = {
        "_linqmd_theme": "dp_3",
        "full_name": "Dr. Test",
        "email": "doc@example.com",
        "specialty": "Cardiology",
        "medical_registration_number": "REG1",
        "medical_council": "Council",
        "year_of_mbbs": 2012,
    }

    db = AsyncMock()
    repo = MagicMock()
    repo.sync_identity_from_doctor = AsyncMock()
    repo.log_status_change = AsyncMock()

    sync_result = LinQMDSyncResult(
        success=False,
        doctor_id=42,
        error_message="LinQMD unavailable",
        linqmd_response={"error": "timeout"},
    )

    with (
        patch(
            "app.services.bulk_csv_post_upload.OnboardingRepository",
            return_value=repo,
        ),
        patch(
            "app.services.bulk_csv_post_upload.LinqmdCredentialsRepository"
        ) as creds_cls,
        patch(
            "app.services.bulk_csv_post_upload.get_linqmd_sync_service"
        ) as get_sync,
    ):
        creds_cls.return_value.exists_for_doctor = AsyncMock(return_value=False)
        get_sync.return_value.sync_doctor_by_id = AsyncMock(return_value=sync_result)

        outcome = await apply_bulk_verify_and_linqmd(
            db=db,
            row=row,
            doctor=doctor,
            identity=identity,
            is_create=True,
            changed_by="admin-1",
            changed_by_email="admin@example.com",
        )

    assert outcome.onboarding_status == OnboardingStatus.VERIFIED.value
    assert outcome.warnings
    assert "LinQMD" in outcome.warnings[0]
    assert doctor.onboarding_status == OnboardingStatus.VERIFIED.value
