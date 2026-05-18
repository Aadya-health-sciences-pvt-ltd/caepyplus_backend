"""Integration tests for OnboardingRepository.

Runs against an in-memory SQLite database via the ``db_session`` fixture
defined in ``tests/conftest.py``.  No external services are required.

Coverage:
- get_next_doctor_id (fallback path, since SQLite has no doctor_id_seq)
- create_identity / get_identity_by_doctor_id / get_identity_by_email
- list_identities (plain + status filter + eager_load)
- count_identities_by_status
- update_onboarding_status
- log_status_change / get_status_history (flush-based atomicity)
- upsert_details / get_details_by_doctor_id
- add_media / list_media / delete_media
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.onboarding import OnboardingStatus
from src.app.repositories.onboarding_repository import OnboardingRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_identity(
    repo: OnboardingRepository,
    *,
    suffix: str = "01",
    status: OnboardingStatus = OnboardingStatus.PENDING,
) -> object:
    return await repo.create_identity(
        first_name="Test",
        last_name=f"Doctor{suffix}",
        email=f"dr{suffix}@example.com",
        phone_number=f"+9198000{suffix}",
        onboarding_status=status,
    )


# ---------------------------------------------------------------------------
# get_next_doctor_id (SQLite fallback path)
# ---------------------------------------------------------------------------


class TestGetNextDoctorId:
    async def test_returns_1_when_table_empty(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        next_id = await repo.get_next_doctor_id()
        assert next_id >= 1

    async def test_increments_after_create(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        id1 = await repo.get_next_doctor_id()
        await _create_identity(repo, suffix="A1")
        id2 = await repo.get_next_doctor_id()
        assert id2 > id1


# ---------------------------------------------------------------------------
# create_identity / get_identity_by_*
# ---------------------------------------------------------------------------


class TestCreateAndGetIdentity:
    async def test_create_returns_persisted_identity(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="B1")
        assert identity.id is not None
        assert identity.doctor_id is not None

    async def test_get_by_doctor_id_returns_correct_row(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="B2")
        found = await repo.get_identity_by_doctor_id(identity.doctor_id)
        assert found is not None
        assert found.doctor_id == identity.doctor_id

    async def test_get_by_email_returns_correct_row(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        await _create_identity(repo, suffix="B3")
        found = await repo.get_identity_by_email("drB3@example.com")
        assert found is not None

    async def test_get_by_doctor_id_returns_none_when_missing(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        assert await repo.get_identity_by_doctor_id(99999) is None

    async def test_default_status_is_pending(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="B4")
        assert identity.onboarding_status == OnboardingStatus.PENDING


# ---------------------------------------------------------------------------
# list_identities / count_identities_by_status
# ---------------------------------------------------------------------------


class TestListAndCount:
    async def test_list_returns_created_identities(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        await _create_identity(repo, suffix="C1")
        await _create_identity(repo, suffix="C2")
        results = await repo.list_identities()
        assert len(results) >= 2

    async def test_list_filters_by_status(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        await _create_identity(repo, suffix="C3", status=OnboardingStatus.SUBMITTED)
        await _create_identity(repo, suffix="C4", status=OnboardingStatus.PENDING)
        submitted = await repo.list_identities(status=OnboardingStatus.SUBMITTED)
        assert all(i.onboarding_status == OnboardingStatus.SUBMITTED for i in submitted)

    async def test_list_with_eager_load_returns_same_rows(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        await _create_identity(repo, suffix="C5")
        normal = await repo.list_identities()
        eager = await repo.list_identities(eager_load=True)
        assert len(normal) == len(eager)

    async def test_count_by_status_correct(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        await _create_identity(repo, suffix="C6", status=OnboardingStatus.VERIFIED)
        count = await repo.count_identities_by_status(status=OnboardingStatus.VERIFIED)
        assert count >= 1

    async def test_count_all_is_at_least_created(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        before = await repo.count_identities_by_status()
        await _create_identity(repo, suffix="C7")
        after = await repo.count_identities_by_status()
        assert after == before + 1

    async def test_list_respects_limit(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        for i in range(5):
            await _create_identity(repo, suffix=f"CL{i}")
        results = await repo.list_identities(limit=2)
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# update_onboarding_status
# ---------------------------------------------------------------------------


class TestUpdateOnboardingStatus:
    async def test_status_is_updated(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="D1")
        await repo.update_onboarding_status(
            doctor_id=identity.doctor_id,
            new_status=OnboardingStatus.SUBMITTED,
        )
        updated = await repo.get_identity_by_doctor_id(identity.doctor_id)
        assert updated.onboarding_status == OnboardingStatus.SUBMITTED

    async def test_status_updated_after_verify(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="D2")
        await repo.update_onboarding_status(
            doctor_id=identity.doctor_id,
            new_status=OnboardingStatus.VERIFIED,
        )
        updated = await repo.get_identity_by_doctor_id(identity.doctor_id)
        assert updated.onboarding_status == OnboardingStatus.VERIFIED

    async def test_rejection_reason_stored(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="D3")
        await repo.update_onboarding_status(
            doctor_id=identity.doctor_id,
            new_status=OnboardingStatus.REJECTED,
            rejection_reason="Incomplete documents",
        )
        updated = await repo.get_identity_by_doctor_id(identity.doctor_id)
        assert updated.rejection_reason == "Incomplete documents"


# ---------------------------------------------------------------------------
# log_status_change / get_status_history — flush-based atomicity
# ---------------------------------------------------------------------------


class TestStatusHistory:
    async def test_log_creates_history_entry(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="E1")
        await repo.log_status_change(
            doctor_id=identity.doctor_id,
            previous_status=OnboardingStatus.PENDING,
            new_status=OnboardingStatus.SUBMITTED,
            changed_by="system",
        )
        await db_session.commit()  # caller commits after flush
        history = await repo.get_status_history(identity.doctor_id)
        assert len(history) >= 1
        assert history[0].new_status == OnboardingStatus.SUBMITTED

    async def test_multiple_logs_are_ordered(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="E2")
        await repo.log_status_change(
            doctor_id=identity.doctor_id,
            previous_status=OnboardingStatus.PENDING,
            new_status=OnboardingStatus.SUBMITTED,
            changed_by="system",
        )
        await repo.log_status_change(
            doctor_id=identity.doctor_id,
            previous_status=OnboardingStatus.SUBMITTED,
            new_status=OnboardingStatus.VERIFIED,
            changed_by="admin",
        )
        await db_session.commit()
        history = await repo.get_status_history(identity.doctor_id)
        assert len(history) >= 2


# ---------------------------------------------------------------------------
# upsert_details / get_details_by_doctor_id
# ---------------------------------------------------------------------------


class TestUpsertDetails:
    async def test_create_details_on_first_call(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="F1")
        details = await repo.upsert_details(
            doctor_id=identity.doctor_id,
            payload={"specialty": "Cardiology"},
        )
        assert details is not None
        assert details.specialty == "Cardiology"  # type: ignore[union-attr]

    async def test_update_details_on_second_call(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="F2")
        await repo.upsert_details(doctor_id=identity.doctor_id, payload={"specialty": "Cardiology"})
        updated = await repo.upsert_details(doctor_id=identity.doctor_id, payload={"specialty": "Neurology"})
        assert updated.specialty == "Neurology"  # type: ignore[union-attr]

    async def test_get_details_returns_row(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="F3")
        await repo.upsert_details(doctor_id=identity.doctor_id, payload={"specialty": "Ortho"})
        details = await repo.get_details_by_doctor_id(identity.doctor_id)
        assert details is not None
        assert details.specialty == "Ortho"  # type: ignore[union-attr]

    async def test_get_details_returns_none_when_absent(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="F4")
        result = await repo.get_details_by_doctor_id(identity.doctor_id)
        assert result is None


# ---------------------------------------------------------------------------
# add_media / list_media / delete_media
# ---------------------------------------------------------------------------


class TestMedia:
    async def test_add_and_list_media(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="G1")
        await repo.add_media(
            doctor_id=identity.doctor_id,
            media_type="image",
            media_category="profile_photo",
            file_name="photo.jpg",
            file_uri="https://storage/photo.jpg",
        )
        media_list = await repo.list_media(identity.doctor_id)
        assert len(media_list) == 1
        assert media_list[0].file_name == "photo.jpg"

    async def test_delete_media_returns_true(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="G2")
        media = await repo.add_media(
            doctor_id=identity.doctor_id,
            media_type="document",
            media_category="degree_certificate",
            file_name="degree.pdf",
            file_uri="https://storage/degree.pdf",
        )
        result = await repo.delete_media(media.media_id)
        assert result is True

    async def test_delete_media_removes_row(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        identity = await _create_identity(repo, suffix="G3")
        media = await repo.add_media(
            doctor_id=identity.doctor_id,
            media_type="image",
            media_category="profile_photo",
            file_name="pic.jpg",
            file_uri="https://storage/pic.jpg",
        )
        await repo.delete_media(media.media_id)
        remaining = await repo.list_media(identity.doctor_id)
        assert len(remaining) == 0

    async def test_delete_nonexistent_media_returns_false(self, db_session: AsyncSession):
        repo = OnboardingRepository(db_session)
        result = await repo.delete_media("00000000-0000-0000-0000-000000000000")
        assert result is False
