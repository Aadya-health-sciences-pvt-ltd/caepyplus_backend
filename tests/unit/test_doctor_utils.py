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

from src.app.core.doctor_utils import synthesise_identity
from src.app.models.doctor import Doctor
from src.app.schemas.onboarding import DoctorIdentityResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doctor(**overrides) -> MagicMock:
    """Return a Doctor-like MagicMock with sensible defaults, optionally overridden.

    MagicMock(spec=Doctor) is used instead of a bare Doctor() instance because
    SQLAlchemy 2.x requires the ORM session-state machinery to be initialised
    before mapped attributes can be set on an out-of-session object.
    MagicMock(spec=Doctor) is duck-typed correctly by synthesise_identity which
    only accesses plain attribute values.
    """
    now = datetime.now(UTC)
    defaults = {
        "id": 1,
        "first_name": "Anjali",
        "last_name": "Sharma",
        "email": "anjali@example.com",
        "phone": "+919876543210",
        "title": "Dr.",
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

    def test_first_and_last_name_preserved(self):
        doctor = _make_doctor(first_name="Priya", last_name="Nair")
        result = synthesise_identity(doctor)
        assert result.first_name == "Priya"
        assert result.last_name == "Nair"

    def test_email_preserved(self):
        doctor = _make_doctor(email="priya@example.com")
        result = synthesise_identity(doctor)
        assert result.email == "priya@example.com"

    def test_phone_mapped_to_phone_number(self):
        doctor = _make_doctor(phone="+918888888888")
        result = synthesise_identity(doctor)
        assert result.phone_number == "+918888888888"

    def test_title_preserved(self):
        doctor = _make_doctor(title="Prof.")
        result = synthesise_identity(doctor)
        assert result.title == "Prof."

    def test_onboarding_status_preserved(self):
        doctor = _make_doctor(onboarding_status="submitted")
        result = synthesise_identity(doctor)
        assert result.onboarding_status == "submitted"

    def test_onboarding_status_defaults_to_pending_when_none(self):
        doctor = _make_doctor(onboarding_status=None)
        result = synthesise_identity(doctor)
        assert result.onboarding_status == "pending"

    def test_is_active_always_true(self):
        """Synthesised identities are always marked active."""
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
        """If doctor.created_at is None, timestamps fall back to datetime.now(UTC)."""
        before = datetime.now(UTC)
        doctor = _make_doctor(created_at=None, updated_at=None)
        result = synthesise_identity(doctor)
        after = datetime.now(UTC)
        assert before <= result.created_at <= after

    def test_null_first_name_becomes_empty_string(self):
        doctor = _make_doctor(first_name=None)
        result = synthesise_identity(doctor)
        assert result.first_name == ""

    def test_null_last_name_becomes_empty_string(self):
        doctor = _make_doctor(last_name=None)
        result = synthesise_identity(doctor)
        assert result.last_name == ""

    def test_null_phone_becomes_empty_string(self):
        doctor = _make_doctor(phone=None)
        result = synthesise_identity(doctor)
        assert result.phone_number == ""
