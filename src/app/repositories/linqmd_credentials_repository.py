"""Repository for doctor_linqmd_credentials table."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.linqmd_credentials import DoctorLinqmdCredentials


class LinqmdCredentialsRepository:
    """CRUD helpers for persisted LinQMD credentials."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_doctor_id(self, doctor_id: int) -> DoctorLinqmdCredentials | None:
        stmt = select(DoctorLinqmdCredentials).where(
            DoctorLinqmdCredentials.doctor_id == doctor_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def exists_for_doctor(self, doctor_id: int) -> bool:
        row = await self.get_by_doctor_id(doctor_id)
        return row is not None

    async def get_synced_doctor_ids(self, doctor_ids: Sequence[int]) -> set[int]:
        if not doctor_ids:
            return set()
        stmt = select(DoctorLinqmdCredentials.doctor_id).where(
            DoctorLinqmdCredentials.doctor_id.in_(doctor_ids)
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def create(
        self,
        *,
        doctor_id: int,
        doctor_name: str,
        linqmd_user_id: str,
        linqmd_username: str,
        linqmd_password: str,
    ) -> DoctorLinqmdCredentials:
        row = DoctorLinqmdCredentials(
            doctor_id=doctor_id,
            doctor_name=doctor_name,
            linqmd_user_id=linqmd_user_id,
            linqmd_username=linqmd_username,
            linqmd_password=linqmd_password,
        )
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ValueError("LinQMD credentials already exist for this doctor") from exc
        return row
