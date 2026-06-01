"""Unit tests for LinQMD sync context (doctors row vs doctor_identity)."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.repositories.doctor_repository import DoctorRepository
from src.app.repositories.onboarding_repository import OnboardingRepository
from src.app.services.linqmd_sync_service import LinQMDSyncService


@pytest.mark.asyncio
async def test_build_sync_context_prefers_doctors_full_name(db_session: AsyncSession) -> None:
    """LinQMD payload contact fields should use doctors row when identity is stale."""
    doc_repo = DoctorRepository(db_session)
    doctor = await doc_repo.create_from_phone("+919876543276")
    doctor.full_name = "Dr Fresh From Doctors"
    await db_session.commit()
    await db_session.refresh(doctor)

    onboarding_repo = OnboardingRepository(db_session)
    await onboarding_repo.create_identity(
        doctor_id=doctor.id,
        email="sync.test@hospital.com",
        phone_number=doctor.phone or "",
        full_name="Dr Stale Identity",
    )

    service = LinQMDSyncService()
    context = await service._build_sync_context(doctor.id, db_session)
    assert context is not None

    identity_dict, _, _ = context
    assert identity_dict["full_name"] == "Dr Fresh From Doctors"
    assert identity_dict["email"] == "sync.test@hospital.com"

    payload = service.transform_doctor_data(
        identity_dict,
        {"specialty": "Cardiology"},
        linqmd_username="testuser",
        linqmd_password="secret",
        include_theme=False,
    )
    assert payload.fullname == "Dr Fresh From Doctors"
