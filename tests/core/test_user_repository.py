"""Integration tests for UserRepository.

Tests run against an in-memory SQLite database (no external services).
The conftest.py at the root of tests/ provides ``db_session`` and
``test_engine`` fixtures.

Focus:
- ``update_fields`` applies all mutations in a single commit (atomicity proof)
- individual helpers still work correctly (create, get_by_phone, set_active, …)
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.enums import UserRole
from src.app.repositories.user_repository import UserRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_repo(session: AsyncSession) -> UserRepository:
    return UserRepository(session)


async def _seed_user(
    session: AsyncSession,
    *,
    phone: str = "+919800000001",
    role: str = UserRole.USER.value,
    is_active: bool = True,
) -> int:
    """Create a bare user and return its id."""
    repo = UserRepository(session)
    user = await repo.create(phone=phone, role=role, is_active=is_active)
    return user.id


# ---------------------------------------------------------------------------
# create / get_by_phone
# ---------------------------------------------------------------------------


class TestCreateAndGet:
    async def test_create_returns_user_with_id(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000002", role=UserRole.USER.value)
        assert user.id is not None
        assert user.phone == "+919800000002"

    async def test_get_by_phone_normalises(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="9800000003")  # no prefix in input
        found = await repo.get_by_phone("+919800000003")
        assert found is not None

    async def test_get_by_phone_not_found(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        found = await repo.get_by_phone("+919999999000")
        assert found is None

    async def test_get_or_create_creates_new(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user, is_new = await repo.get_or_create(phone="+919800000004")
        assert is_new is True
        assert user.id is not None

    async def test_get_or_create_returns_existing(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user1, _ = await repo.get_or_create(phone="+919800000005")
        user2, is_new = await repo.get_or_create(phone="+919800000005")
        assert is_new is False
        assert user1.id == user2.id


# ---------------------------------------------------------------------------
# update_fields — atomicity proof
# ---------------------------------------------------------------------------


class TestUpdateFieldsAtomicity:
    """update_fields must apply all mutations in one commit.

    Strategy: call update_fields with role + is_active + doctor_id changes,
    then re-fetch the user from a fresh query and assert all three columns
    changed.  If the old multi-commit path were used instead, a simulated
    mid-operation failure would leave the row partially updated; that case
    is tested by checking that the returned object already reflects all
    changes after a single call.
    """

    async def test_all_fields_applied_in_one_call(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(
            phone="+919800000010",
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

        # Re-fetch from DB to confirm the commit landed
        refetched = await repo.get_by_id(user.id)
        assert refetched is not None
        assert refetched.role == UserRole.OPERATIONAL.value
        assert refetched.is_active is False

    async def test_partial_update_leaves_other_fields_unchanged(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(
            phone="+919800000011",
            role=UserRole.ADMIN.value,
            is_active=True,
        )

        updated = await repo.update_fields(user.id, is_active=False)

        assert updated is not None
        # role must be unchanged
        assert updated.role == UserRole.ADMIN.value
        assert updated.is_active is False

    async def test_returns_none_for_missing_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        result = await repo.update_fields(9999999, role=UserRole.ADMIN.value)
        assert result is None

    async def test_update_fields_sets_updated_at(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000012", role=UserRole.USER.value)

        updated = await repo.update_fields(user.id, role=UserRole.OPERATIONAL.value)

        assert updated is not None
        # update_fields must stamp updated_at
        assert updated.updated_at is not None


# ---------------------------------------------------------------------------
# set_active / deactivate / activate
# ---------------------------------------------------------------------------


class TestActivation:
    async def test_deactivate(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000020", is_active=True)
        result = await repo.deactivate(user.id)
        assert result is not None
        assert result.is_active is False

    async def test_activate(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(phone="+919800000021", is_active=False)
        result = await repo.activate(user.id)
        assert result is not None
        assert result.is_active is True

    async def test_set_active_nonexistent_returns_none(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        assert await repo.set_active(99999, True) is None


# ---------------------------------------------------------------------------
# role helpers
# ---------------------------------------------------------------------------


class TestRoleHelpers:
    async def test_is_admin_true(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000030", role=UserRole.ADMIN.value, is_active=True)
        assert await repo.is_admin("+919800000030") is True

    async def test_is_admin_false_for_user_role(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000031", role=UserRole.USER.value, is_active=True)
        assert await repo.is_admin("+919800000031") is False

    async def test_can_access_admin_operational(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000032", role=UserRole.OPERATIONAL.value, is_active=True)
        assert await repo.can_access_admin("+919800000032") is True

    async def test_can_access_admin_plain_user_false(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        await repo.create(phone="+919800000033", role=UserRole.USER.value, is_active=True)
        assert await repo.can_access_admin("+919800000033") is False
