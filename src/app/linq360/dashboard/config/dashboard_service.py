"""Dashboard business logic (glance, webhook, content engagement)."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from ...common.base_service import BaseService
from ...glance_shapes import (
    TODAYS_SCHEDULE_KEY,
    appointments_glance_response,
    content_glance_response,
    count_document,
    merge_glance_response,
    normalize_todays_schedule,
    workspace_id_or_zero,
)
from ...models.dashboard import WorkspaceDoctorDashboard
from ...services.practice_hub_pending_client import (
    PracticeHubPendingError,
    fetch_pending_counts,
    workspace_identity_from_token,
)
from ..dashboard_content import content_block, payload_from_stored_content
from ..dashboard_repository import DashboardRepository, GlanceDashboardMissing

__all__ = ["DashboardService", "GlanceDashboardMissing"]

logger = logging.getLogger(__name__)


class DashboardService(BaseService):
    """Orchestrates dashboard repository + Practice Hub pending sync."""

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.repo = DashboardRepository(session)

    async def clear_all_workspace_dashboards(self) -> int:
        """Delete all workspace_doctor_dashboard rows."""
        deleted = await self.repo.delete_all_workspace_dashboards()
        logger.info("workspace_doctor_dashboard_cleared deleted=%s", deleted)
        return deleted

    async def get_content_glance(self, linqmd_user_id: str) -> dict[str, Any]:
        """Content-only document from ``doctor_dashboard.todays_glance``."""
        uid = str(linqmd_user_id).strip()
        doctor = await self.repo.get_doctor_dashboard(uid)
        stored = (
            doctor.todays_glance
            if doctor is not None and doctor.todays_glance
            else None
        )
        return content_glance_response(content_block(payload_from_stored_content(stored)))

    async def get_appointments_glance(
        self,
        linqmd_user_id: str,
        *,
        workspace_id: int,
        ws_user_id: int | None = None,
    ) -> dict[str, Any]:
        """Appointments-only document from ``workspace_doctor_dashboard``."""
        uid = str(linqmd_user_id).strip()
        ws_id = workspace_id_or_zero(workspace_id)
        workspace = await self.repo.get_workspace_dashboard(
            uid, ws_id, ws_user_id=ws_user_id
        )
        return appointments_glance_response(
            requests=workspace.requests if workspace is not None else 0,
            appointments=workspace.appointments if workspace is not None else 0,
            appointment_json=(
                workspace.appointment_json if workspace is not None else None
            ),
        )

    async def get_glance(
        self,
        linqmd_user_id: str,
        *,
        workspace_id: int | None = None,
        ws_user_id: int | None = None,
    ) -> dict[str, Any]:
        """Merged glance (legacy / WS when both sections are needed)."""
        uid = str(linqmd_user_id).strip()
        content = await self.get_content_glance(uid)
        appointments = await self.get_appointments_glance(
            uid,
            workspace_id=workspace_id_or_zero(workspace_id),
            ws_user_id=ws_user_id,
        )
        return merge_glance_response(
            content["content"],
            requests=appointments.get("requests"),
            appointments=appointments.get("appointments"),
            appointment_json={TODAYS_SCHEDULE_KEY: appointments.get(TODAYS_SCHEDULE_KEY)},
        )

    async def upsert_pending_glance(
        self,
        linqmd_user_id: str,
        payload: dict[str, Any],
        *,
        workspace_id: int | None = None,
        ws_user_id: int | None = None,
    ) -> None:
        uid = str(linqmd_user_id).strip()
        doctor = await self.repo.ensure_doctor_dashboard(uid, ws_user_id=ws_user_id)
        doctor.todays_glance = content_block(payload)
        flag_modified(doctor, "todays_glance")
        await self.repo.ensure_workspace_dashboard(
            uid,
            workspace_id=workspace_id,
            ws_user_id=ws_user_id,
        )
        await self.session.flush()

    async def sync_pending_glance(self, workspace_access_token: str) -> dict[str, Any]:
        """Pull Practice Hub pending counts; return content-only envelope."""
        identity = workspace_identity_from_token(
            workspace_access_token,
            require_ph_user_id=True,
            require_workspace_id=False,
        )
        uid = str(identity["linqmd_user_id"])
        payload = await fetch_pending_counts(workspace_access_token)
        workspace_id = identity.get("workspace_id")
        ws_user = identity.get("ws_user_id")
        await self.upsert_pending_glance(
            uid,
            payload,
            workspace_id=workspace_id,
            ws_user_id=ws_user,
        )
        return await self.get_content_glance(uid)

    async def upsert_workspace_schedule(
        self,
        *,
        ph_user_id: int,
        workspace_id: int,
        ws_user_id: int | None = None,
        appointments: int = 0,
        requests: int = 0,
        todays_schedule: list[dict[str, Any]] | None = None,
    ) -> WorkspaceDoctorDashboard:
        uid = str(ph_user_id)
        row = await self.repo.ensure_workspace_dashboard(
            uid,
            workspace_id=workspace_id,
            ws_user_id=ws_user_id,
        )
        schedule = todays_schedule if isinstance(todays_schedule, list) else []
        row.appointments = count_document(appointments)
        row.requests = count_document(requests)
        row.appointment_json = normalize_todays_schedule(
            {TODAYS_SCHEDULE_KEY: schedule}
        )
        flag_modified(row, "appointments")
        flag_modified(row, "requests")
        flag_modified(row, "appointment_json")
        await self.session.flush()
        return row

    async def process_dashboard_webhook(
        self,
        *,
        ph_user_id: int,
        ws_user_id: int,
        workspace_id: int,
        event_type: str | None = None,
        appointments: int = 0,
        requests: int = 0,
        todays_schedule: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Apply schedule from body identity (no Bearer); return appointments glance."""
        from ..realtime.event_map import (
            DashboardSection,
            sections_for_event,
        )
        from ..realtime.refresh_service import enqueue_dashboard_event

        resolved_workspace_id = workspace_id_or_zero(workspace_id)
        if resolved_workspace_id <= 0:
            raise PracticeHubPendingError(
                "workspace_id is required in the webhook body",
                status_code=400,
            )
        if ws_user_id is None or int(ws_user_id) <= 0:
            raise PracticeHubPendingError(
                "ws_user_id is required in the webhook body for debounce grouping",
                status_code=400,
            )

        sections = set(sections_for_event(event_type))
        if (
            DashboardSection.APPOINTMENTS in sections
            or DashboardSection.REQUESTS in sections
        ):
            await self.upsert_workspace_schedule(
                ph_user_id=int(ph_user_id),
                workspace_id=int(resolved_workspace_id),
                ws_user_id=int(ws_user_id),
                appointments=appointments,
                requests=requests,
                todays_schedule=todays_schedule,
            )

        enqueue_dashboard_event(
            ws_user_id=int(ws_user_id),
            workspace_id=int(resolved_workspace_id),
            sections=sections,
            context={
                "ph_user_id": int(ph_user_id),
                "appointments": appointments,
                "requests": requests,
                "todays_schedule": todays_schedule or [],
                "event_type": event_type,
            },
        )

        return await self.get_appointments_glance(
            str(ph_user_id),
            workspace_id=int(resolved_workspace_id),
            ws_user_id=int(ws_user_id),
        )

    async def get_engagement(self, doctor_id: int) -> dict[str, Any]:
        from ...services.content_aggregator_service import ContentAggregatorService

        return await ContentAggregatorService(self.session).get_engagement(doctor_id)
