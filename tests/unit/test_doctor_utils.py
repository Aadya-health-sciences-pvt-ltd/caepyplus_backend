"""Unit tests for src/app/core/doctor_utils.py.

``synthesise_identity`` builds a ``DoctorIdentityResponse`` from a bare
``Doctor`` ORM row (one that has no matching doctor_identity row).

All tests are pure in-process — no DB, no HTTP, no external services.
The ``Doctor`` model is instantiated directly without committing to a DB.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.app.core.doctor_utils import (
    is_synthetic_identity_email,
    is_synthetic_identity_full_name,
    is_synthetic_identity_phone,
    resolve_display_email,
    resolve_display_full_name,
    resolve_display_phone,
    normalize_onboarding_status_value,
    resolve_onboarding_status_for_response,
    should_preserve_verified_on_profile_resubmit,
    synthesise_identity,
)
from src.app.models.doctor import Doctor
from src.app.schemas.onboarding import DoctorIdentityResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doctor(**overrides) -> MagicMock:
    """Return a Doctor-like MagicMock with sensible defaults, optionally overridden."""
    now = datetime.now(UTC)
    defaults = {
        "id": 1,
        "full_name": "Anjali Sharma",
        "email": "anjali@example.com",
        "phone": "+919876543210",
        "onboarding_status": "pending",
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    doctor = MagicMock(spec=Doctor)
    for k, v in defaults.items():
        setattr(doctor, k, v)
    return doctor


# ---------------------------------------------------------------------------
# Synthetic identity field detection
# ---------------------------------------------------------------------------


class TestPreserveVerifiedOnResubmit:

    def test_preserves_when_doctors_row_verified(self):
        assert should_preserve_verified_on_profile_resubmit("verified", "submitted")

    def test_preserves_when_identity_verified(self):
        assert should_preserve_verified_on_profile_resubmit("submitted", "verified")

    def test_does_not_preserve_for_pending(self):
        assert not should_preserve_verified_on_profile_resubmit("pending", "pending")


class TestResolveOnboardingStatusForResponse:

    def test_verified_wins_when_doctors_row_verified_identity_submitted(self):
        assert resolve_onboarding_status_for_response(
            "submitted",
            "verified",
        ) == "verified"

    def test_verified_wins_when_identity_verified_doctors_pending(self):
        assert resolve_onboarding_status_for_response(
            "verified",
            "pending",
        ) == "verified"

    def test_uses_identity_when_no_verified_mismatch(self):
        assert resolve_onboarding_status_for_response(
            "submitted",
            "pending",
        ) == "submitted"

    def test_falls_back_to_doctors_row_without_identity(self):
        assert resolve_onboarding_status_for_response(
            None,
            "submitted",
            has_identity_row=False,
        ) == "submitted"


class TestSyntheticIdentityFields:

    def test_placeholder_email_is_synthetic(self):
        assert is_synthetic_identity_email("placeholder_42@caepy.com")

    def test_real_email_is_not_synthetic(self):
        assert not is_synthetic_identity_email("dr@example.com")

    def test_displaced_email_is_synthetic(self):
        assert is_synthetic_identity_email("_displaced_abcd1234@placeholder")

    def test_empty_email_is_synthetic(self):
        assert is_synthetic_identity_email("")
        assert is_synthetic_identity_email(None)

    def test_doctor_placeholder_name_is_synthetic(self):
        assert is_synthetic_identity_full_name("Doctor 42", doctor_id=42)
        assert is_synthetic_identity_full_name("doctor 7")

    def test_real_name_is_not_synthetic(self):
        assert not is_synthetic_identity_full_name("Anjali Sharma")

    def test_unknown_phone_is_synthetic(self):
        assert is_synthetic_identity_phone("UNKNOWN_99", doctor_id=99)
        assert is_synthetic_identity_phone("unknown_5")

    def test_real_phone_is_not_synthetic(self):
        assert not is_synthetic_identity_phone("+919876543210")


class TestResolveDisplayFields:

    def test_resolve_display_email_prefers_doctors_row_when_identity_placeholder(self):
        assert resolve_display_email(
            "placeholder_1@caepy.com",
            "real@example.com",
        ) == "real@example.com"

    def test_resolve_display_full_name_prefers_doctors_row(self):
        assert resolve_display_full_name(
            "Doctor 1",
            "Priya Nair",
            doctor_id=1,
        ) == "Priya Nair"

    def test_resolve_display_phone_prefers_doctors_row(self):
        assert resolve_display_phone(
            "UNKNOWN_3",
            "+918888888888",
            doctor_id=3,
        ) == "+918888888888"

    def test_resolve_display_email_prefers_real_identity_email(self):
        assert resolve_display_email("real@example.com", "other@example.com") == "real@example.com"

    def test_resolve_display_email_skips_pending_doctor_email(self):
        assert resolve_display_email(
            "placeholder_1@caepy.com",
            "pending_user@example.com",
        ) == "placeholder_1@caepy.com"

    def test_resolve_display_full_name_falls_back_to_identity(self):
        assert resolve_display_full_name(
            "Priya Nair",
            "Doctor 9",
            doctor_id=9,
        ) == "Priya Nair"

    def test_resolve_display_phone_falls_back_to_identity(self):
        assert resolve_display_phone(
            "+919111111111",
            "UNKNOWN_9",
            doctor_id=9,
        ) == "+919111111111"


class TestNormalizeOnboardingStatusValue:

    def test_none_returns_empty_string(self):
        assert normalize_onboarding_status_value(None) == ""

    def test_enum_like_value_is_lowercased(self):
        class _Status:
            value = "Verified"

        assert normalize_onboarding_status_value(_Status()) == "verified"


# ---------------------------------------------------------------------------
# synthesise_identity — correctness
# ---------------------------------------------------------------------------


class TestSynthesiseIdentity:

    def test_returns_doctor_identity_response_type(self):
        doctor = _make_doctor()
        result = synthesise_identity(doctor)
        assert isinstance(result, DoctorIdentityResponse)

    def test_id_is_stringified_doctor_id(self):
        doctor = _make_doctor(id=99)
        result = synthesise_identity(doctor)
        assert result.id == "99"
        assert result.doctor_id == 99

    def test_full_name_preserved(self):
        doctor = _make_doctor(full_name="Priya Nair")
        result = synthesise_identity(doctor)
        assert result.full_name == "Priya Nair"

    def test_email_preserved(self):
        doctor = _make_doctor(email="priya@example.com")
        result = synthesise_identity(doctor)
        assert result.email == "priya@example.com"

    def test_phone_mapped_to_phone_number(self):
        doctor = _make_doctor(phone="+918888888888")
        result = synthesise_identity(doctor)
        assert result.phone_number == "+918888888888"

    def test_onboarding_status_preserved(self):
        doctor = _make_doctor(onboarding_status="submitted")
        result = synthesise_identity(doctor)
        assert result.onboarding_status == "submitted"

    def test_onboarding_status_defaults_to_pending_when_none(self):
        doctor = _make_doctor(onboarding_status=None)
        result = synthesise_identity(doctor)
        assert result.onboarding_status == "pending"

    def test_is_active_always_true(self):
        doctor = _make_doctor()
        result = synthesise_identity(doctor)
        assert result.is_active is True

    def test_audit_fields_are_none(self):
        doctor = _make_doctor()
        result = synthesise_identity(doctor)
        assert result.status_updated_at is None
        assert result.status_updated_by is None
        assert result.rejection_reason is None
        assert result.verified_at is None
        assert result.deleted_at is None

    def test_timestamps_use_doctor_created_at(self):
        fixed = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        doctor = _make_doctor(created_at=fixed, updated_at=fixed)
        result = synthesise_identity(doctor)
        assert result.registered_at == fixed
        assert result.created_at == fixed
        assert result.updated_at == fixed

    def test_null_created_at_falls_back_to_utc_now(self):
        before = datetime.now(UTC)
        doctor = _make_doctor(created_at=None, updated_at=None)
        result = synthesise_identity(doctor)
        after = datetime.now(UTC)
        assert before <= result.created_at <= after

    def test_null_full_name_becomes_empty_string(self):
        doctor = _make_doctor(full_name=None)
        result = synthesise_identity(doctor)
        assert result.full_name == ""

    def test_null_phone_becomes_empty_string(self):
        doctor = _make_doctor(phone=None)
        result = synthesise_identity(doctor)
        assert result.phone_number == ""
