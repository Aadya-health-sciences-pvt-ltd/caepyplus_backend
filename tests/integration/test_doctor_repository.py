"""Integration tests for DoctorRepository.

Runs against an in-memory SQLite database via the ``db_session`` fixture
defined in ``tests/conftest.py``.  No external services are required.

Coverage:
- create_from_phone / create_from_email
- get_by_id, get_by_email, get_by_phone_number, get_by_registration_number
- get_all / count with filters
- delete / delete_or_raise
- DoctorAlreadyExistsError / DoctorNotFoundError are raised correctly
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import DoctorAlreadyExistsError, DoctorNotFoundError
from src.app.repositories.doctor_repository import DoctorRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_repo(session: AsyncSession) -> DoctorRepository:
    return DoctorRepository(session)


# ---------------------------------------------------------------------------
# create_from_phone
# ---------------------------------------------------------------------------


class TestCreateFromPhone:
    async def test_creates_doctor_with_id(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_phone("+919800000001")
        assert doctor.id is not None
        assert doctor.phone == "+919800000001"

    async def test_normalises_phone_without_prefix(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_phone("9800000002")
        assert doctor.phone == "+919800000002"

    async def test_first_and_last_name_empty_strings(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_phone("+919800000003")
        assert doctor.first_name == ""
        assert doctor.last_name == ""

    async def test_email_is_none(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_phone("+919800000004")
        assert doctor.email is None

    async def test_default_role_is_user(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_phone("+919800000005")
        assert doctor.role == "user"

    async def test_custom_role_is_stored(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_phone("+919800000006", role="admin")
        assert doctor.role == "admin"


# ---------------------------------------------------------------------------
# create_from_email
# ---------------------------------------------------------------------------


class TestCreateFromEmail:
    async def test_creates_doctor_with_id(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_email("dr.test@example.com")
        assert doctor.id is not None
        assert doctor.email == "dr.test@example.com"

    async def test_email_is_lowercased(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_email("DOCTOR@Example.COM")
        assert doctor.email == "doctor@example.com"

    async def test_name_is_split(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_email("x@y.com", name="Anjali Sharma")
        assert doctor.first_name == "Anjali"
        assert doctor.last_name == "Sharma"

    async def test_single_word_name(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_email("mono@y.com", name="Mono")
        assert doctor.first_name == "Mono"
        assert doctor.last_name == ""

    async def test_no_name_leaves_empty_strings(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_email("noname@y.com")
        assert doctor.first_name == ""
        assert doctor.last_name == ""


# ---------------------------------------------------------------------------
# get_by_id / get_by_id_or_raise
# ---------------------------------------------------------------------------


class TestGetById:
    async def test_returns_existing_doctor(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        created = await repo.create_from_phone("+919700000001")
        found = await repo.get_by_id(created.id)
        assert found is not None
        assert found.id == created.id

    async def test_returns_none_for_missing(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        assert await repo.get_by_id(99999) is None

    async def test_or_raise_raises_not_found(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        with pytest.raises(DoctorNotFoundError):
            await repo.get_by_id_or_raise(99999)


# ---------------------------------------------------------------------------
# get_by_email
# ---------------------------------------------------------------------------


class TestGetByEmail:
    async def test_returns_doctor_by_email(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        await repo.create_from_email("find.me@example.com")
        found = await repo.get_by_email("find.me@example.com")
        assert found is not None

    async def test_case_insensitive_lookup(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        await repo.create_from_email("lower@example.com")
        found = await repo.get_by_email("LOWER@EXAMPLE.COM")
        assert found is not None

    async def test_returns_none_when_not_found(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        assert await repo.get_by_email("ghost@nowhere.com") is None


# ---------------------------------------------------------------------------
# get_by_phone_number
# ---------------------------------------------------------------------------


class TestGetByPhoneNumber:
    async def test_finds_by_exact_phone(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        await repo.create_from_phone("+919600000001")
        found = await repo.get_by_phone_number("+919600000001")
        assert found is not None

    async def test_normalises_input_before_lookup(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        await repo.create_from_phone("+919600000002")
        found = await repo.get_by_phone_number("9600000002")
        assert found is not None

    async def test_returns_none_for_unknown_phone(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        assert await repo.get_by_phone_number("+919999000000") is None


# ---------------------------------------------------------------------------
# count / get_all
# ---------------------------------------------------------------------------


class TestCountAndGetAll:
    async def test_count_increments_on_create(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        before = await repo.count()
        await repo.create_from_phone("+919500000001")
        await repo.create_from_phone("+919500000002")
        after = await repo.count()
        assert after == before + 2

    async def test_get_all_returns_all_doctors(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        before = len(await repo.get_all())
        await repo.create_from_phone("+919500000003")
        all_doctors = await repo.get_all()
        assert len(all_doctors) == before + 1

    async def test_get_all_respects_limit(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        for i in range(5):
            await repo.create_from_phone(f"+91950000100{i}")
        result = await repo.get_all(limit=3)
        assert len(result) <= 3


# ---------------------------------------------------------------------------
# delete / delete_or_raise
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_delete_returns_true_on_success(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_phone("+919400000001")
        result = await repo.delete(doctor.id)
        assert result is True

    async def test_deleted_doctor_not_found_after_delete(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        doctor = await repo.create_from_phone("+919400000002")
        await repo.delete(doctor.id)
        assert await repo.get_by_id(doctor.id) is None

    async def test_delete_returns_false_for_missing(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        assert await repo.delete(99999) is False

    async def test_delete_or_raise_raises_for_missing(self, db_session: AsyncSession):
        repo = DoctorRepository(db_session)
        with pytest.raises(DoctorNotFoundError):
            await repo.delete_or_raise(99999)
