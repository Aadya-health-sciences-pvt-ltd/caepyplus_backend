"""Dashboard data access (workspace_doctor_dashboard + doctor_dashboard)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from ..common.base_repository import BaseRepository
from ..glance_shapes import empty_todays_schedule, normalize_todays_schedule, workspace_id_or_zero
from ..models.dashboard import DoctorDashboard, WorkspaceDoctorDashboard


class GlanceDashboardMissing(Exception):
    """Cannot store glance for a non-numeric Drupal uid."""

    def __init__(self, linqmd_user_id: str) -> None:
        super().__init__(
            "Cannot store linq360.doctor_dashboard.todays_glance for ph_user_id="
            f"{linqmd_user_id} (must be numeric)."
        )
        self.linqmd_user_id = linqmd_user_id


class DashboardRepository(BaseRepository[WorkspaceDoctorDashboard]):
    """Repository for LinQ360 dashboard tables."""

    model = WorkspaceDoctorDashboard

    async def get_workspace_dashboard(
        self,
        linqmd_user_id: str,
        workspace_id: int,
        *,
        ws_user_id: int | None = None,
    ) -> WorkspaceDoctorDashboard | None:
        if not linqmd_user_id.isdigit():
            return None
        clauses = [
            WorkspaceDoctorDashboard.ph_user_id == int(linqmd_user_id),
            WorkspaceDoctorDashboard.workspace_id == int(workspace_id),
        ]
        if ws_user_id is not None:
            clauses.append(WorkspaceDoctorDashboard.ws_user_id == int(ws_user_id))
        else:
            clauses.append(WorkspaceDoctorDashboard.ws_user_id.is_(None))
        result = await self.session.execute(
            select(WorkspaceDoctorDashboard).where(*clauses)
        )
        row = result.scalar_one_or_none()
        if row is None and ws_user_id is not None:
            result = await self.session.execute(
                select(WorkspaceDoctorDashboard).where(
                    WorkspaceDoctorDashboard.ph_user_id == int(linqmd_user_id),
                    WorkspaceDoctorDashboard.workspace_id == int(workspace_id),
                    WorkspaceDoctorDashboard.ws_user_id.is_(None),
                )
            )
            row = result.scalar_one_or_none()
        return row

    async def get_doctor_dashboard(self, linqmd_user_id: str) -> DoctorDashboard | None:
        if not linqmd_user_id.isdigit():
            return None
        result = await self.session.execute(
            select(DoctorDashboard).where(
                DoctorDashboard.ph_user_id == int(linqmd_user_id)
            )
        )
        return result.scalar_one_or_none()

    async def ensure_workspace_dashboard(
        self,
        linqmd_user_id: str,
        *,
        workspace_id: int | None = None,
        ws_user_id: int | None = None,
    ) -> WorkspaceDoctorDashboard:
        if not linqmd_user_id.isdigit():
            raise GlanceDashboardMissing(linqmd_user_id)
        ws_id = workspace_id_or_zero(workspace_id)
        resolved_ws = int(ws_user_id) if ws_user_id is not None else None
        row = await self.get_workspace_dashboard(
            linqmd_user_id, ws_id, ws_user_id=resolved_ws
        )
        if row is not None:
            if resolved_ws is not None and row.ws_user_id is None:
                row.ws_user_id = resolved_ws
            normalized = normalize_todays_schedule(row.appointment_json)
            if row.appointment_json != normalized:
                row.appointment_json = normalized
                flag_modified(row, "appointment_json")
            await self.flush()
            return row
        row = WorkspaceDoctorDashboard(
            appointment_json=empty_todays_schedule(),
            workspace_id=ws_id,
            ws_user_id=resolved_ws,
            ph_user_id=int(linqmd_user_id),
            requests={},
            appointments={},
        )
        return await self.add(row)

    async def ensure_doctor_dashboard(
        self,
        linqmd_user_id: str,
        *,
        ws_user_id: int | None = None,
    ) -> DoctorDashboard:
        if not linqmd_user_id.isdigit():
            raise GlanceDashboardMissing(linqmd_user_id)
        row = await self.get_doctor_dashboard(linqmd_user_id)
        if row is not None:
            if ws_user_id is not None:
                row.ws_user_id = int(ws_user_id)
            await self.flush()
            return row
        row = DoctorDashboard(
            ph_user_id=int(linqmd_user_id),
            ws_user_id=int(ws_user_id) if ws_user_id is not None else None,
            todays_glance={},
        )
        self.session.add(row)
        await self.flush()
        return row
