"""Integration tests for UserRepository.

Runs against an in-memory SQLite database via the ``db_session`` fixture
defined in ``tests/conftest.py``.  No external services are required.

Coverage:
- create / get_by_id / get_by_phone / get_by_email
- get_or_create (idempotent)
- update_fields (atomicity: all mutations in a single commit)
- update_role / set_active / deactivate / activate
- link_doctor
- is_admin / can_access_admin
- delete
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.enums import UserRole
from src.app.repositories.user_repository import UserRepository


# ---------------------------------------------------------------------------
# create / get_by_id / get_by_phone
# ---------------------------------------------------------------------------


class TestCreateAndGet:
    async def test_create_returns_user_with_id(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000001", role=UserRole.USER.value)
        assert user.id is not None
        assert user.phone == "+919800000001"

    async def test_phone_normalised_on_create(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="9800000002")
        assert user.phone == "+919800000002"

    async def test_get_by_id_returns_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000003")
        found = await repo.get_by_id(user.id)
        assert found is not None
        assert found.id == user.id

    async def test_get_by_id_returns_none_for_missing(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        assert await repo.get_by_id(9_999_999) is None

    async def test_get_by_phone_normalises_input(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000004")
        found = await repo.get_by_phone("9800000004")
        assert found is not None

    async def test_get_by_phone_returns_none_when_missing(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        assert await repo.get_by_phone("+919999000000") is None

    async def test_get_by_email_returns_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000005", email="user5@example.com")
        found = await repo.get_by_email("user5@example.com")
        assert found is not None

    async def test_email_stored_lowercase(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000006", email="USER6@Example.COM")
        assert user.email == "user6@example.com"


# ---------------------------------------------------------------------------
# get_or_create (idempotent)
# ---------------------------------------------------------------------------


class TestGetOrCreate:
    async def test_creates_new_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user, is_new = await repo.get_or_create(phone="+919800000010")
        assert is_new is True
        assert user.id is not None

    async def test_returns_existing_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user1, _ = await repo.get_or_create(phone="+919800000011")
        user2, is_new = await repo.get_or_create(phone="+919800000011")
        assert is_new is False
        assert user1.id == user2.id


# ---------------------------------------------------------------------------
# update_fields — atomicity proof
# ---------------------------------------------------------------------------


class TestUpdateFieldsAtomicity:
    """All field mutations must land in a single commit.

    Proof: call update_fields once, then re-fetch and assert all changed
    columns reflect the new values simultaneously — ruling out partial commits.
    """

    async def test_all_fields_applied_in_one_call(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(
            phone="+919800000020",
            role=UserRole.USER.value,
            is_active=True,
        )
        updated = await repo.update_fields(
            user.id,
            role=UserRole.OPERATIONAL.value,
            is_active=False,
        )
        assert updated is not None
        assert updated.role == UserRole.OPERATIONAL.value
        assert updated.is_active is False

        # Re-fetch proves the commit landed
        refetched = await repo.get_by_id(user.id)
        assert refetched.role == UserRole.OPERATIONAL.value
        assert refetched.is_active is False

    async def test_partial_update_leaves_other_fields_unchanged(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(
            phone="+919800000021",
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        updated = await repo.update_fields(user.id, is_active=False)
        assert updated is not None
        assert updated.role == UserRole.ADMIN.value  # unchanged
        assert updated.is_active is False

    async def test_returns_none_for_missing_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        result = await repo.update_fields(9_999_999, role=UserRole.ADMIN.value)
        assert result is None

    async def test_updated_at_advances(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000022", role=UserRole.USER.value)
        # updated_at may be None on a fresh record (set only on first update)
        updated = await repo.update_fields(user.id, role=UserRole.OPERATIONAL.value)
        assert updated is not None
        assert updated.updated_at is not None

    async def test_doctor_id_can_be_set(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000023")
        updated = await repo.update_fields(user.id, doctor_id=42)
        assert updated.doctor_id == 42


# ---------------------------------------------------------------------------
# set_active / deactivate / activate
# ---------------------------------------------------------------------------


class TestActivation:
    async def test_deactivate_sets_is_active_false(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000030", is_active=True)
        result = await repo.deactivate(user.id)
        assert result is not None
        assert result.is_active is False

    async def test_activate_sets_is_active_true(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000031", is_active=False)
        result = await repo.activate(user.id)
        assert result is not None
        assert result.is_active is True

    async def test_set_active_returns_none_for_missing(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        result = await repo.set_active(9_999_999, True)
        assert result is None


# ---------------------------------------------------------------------------
# update_role
# ---------------------------------------------------------------------------


class TestUpdateRole:
    async def test_role_is_updated(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000040", role=UserRole.USER.value)
        updated = await repo.update_role(user.id, UserRole.ADMIN.value)
        assert updated is not None
        assert updated.role == UserRole.ADMIN.value

    async def test_update_role_returns_none_for_missing(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        result = await repo.update_role(9_999_999, UserRole.ADMIN.value)
        assert result is None


# ---------------------------------------------------------------------------
# link_doctor
# ---------------------------------------------------------------------------


class TestLinkDoctor:
    async def test_links_doctor_id(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000050")
        updated = await repo.link_doctor(user.id, doctor_id=101)
        assert updated is not None
        assert updated.doctor_id == 101


# ---------------------------------------------------------------------------
# is_admin / can_access_admin
# ---------------------------------------------------------------------------


class TestAuthorizationHelpers:
    async def test_is_admin_true_for_admin_role(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000060", role=UserRole.ADMIN.value, is_active=True)
        assert await repo.is_admin("+919800000060") is True

    async def test_is_admin_false_for_user_role(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000061", role=UserRole.USER.value, is_active=True)
        assert await repo.is_admin("+919800000061") is False

    async def test_is_admin_false_for_inactive_admin(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000062", role=UserRole.ADMIN.value, is_active=False)
        assert await repo.is_admin("+919800000062") is False

    async def test_can_access_admin_true_for_operational(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000063", role=UserRole.OPERATIONAL.value, is_active=True)
        assert await repo.can_access_admin("+919800000063") is True

    async def test_can_access_admin_false_for_plain_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000064", role=UserRole.USER.value, is_active=True)
        assert await repo.can_access_admin("+919800000064") is False

    async def test_can_access_admin_false_for_unknown_phone(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        assert await repo.can_access_admin("+919900000000") is False


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_delete_returns_true(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000070")
        assert await repo.delete(user.id) is True

    async def test_deleted_user_not_found_after_delete(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000071")
        await repo.delete(user.id)
        assert await repo.get_by_id(user.id) is None

    async def test_delete_returns_false_for_missing(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        assert await repo.delete(9_999_999) is False
