"""Dashboard HTTP handlers (glance, webhook, content engagement).

Routes are registered in ``dashboard.config.routing``.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, status

from ...core.rbac import get_current_user
from ...db.session import DbSession
from ...models.enums import UserRole
from ...models.user import User
from ...repositories.doctor_repository import DoctorRepository
from ..common.base_controller import BaseController
from ..config.auth import (
    WorkspaceSelectAuth,
    require_dashboard_webhook_auth,
    require_workspace_select_auth,
)
from ..services.practice_hub_pending_client import PracticeHubPendingError
from .config.dashboard_service import DashboardService, GlanceDashboardMissing
from .dashboard_fields import (
    ContentEngagementResponse,
    DashboardWebhookPayload,
    GlanceApiResponse,
)
from .dashboard_response import DashboardResponse

_MSG_GLANCE_GET = "Glance retrieved successfully"
_MSG_GLANCE_SYNC = "Glance synced successfully"
_MSG_DASHBOARD_WEBHOOK = "Dashboard webhook processed successfully"


class DashboardController(BaseController):
    """Thin HTTP adapter over DashboardService."""

    def __init__(self) -> None:
        self.dashboard_response = DashboardResponse()


_controller = DashboardController()


async def require_doctor_engagement_access(
    doctor_id: int,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> int:
    doctor = await DoctorRepository(db).get_by_id(doctor_id)
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    privileged = {
        UserRole.ADMIN.value,
        UserRole.OPERATION.value,
        UserRole.CONTENT_CREATOR.value,
    }
    if user.role in privileged:
        return doctor_id
    if user.doctor_id is not None and int(user.doctor_id) == doctor_id:
        return doctor_id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not allowed to view this doctor's content engagement",
    )


async def get_content_engagement(
    doctor_id: Annotated[int, Depends(require_doctor_engagement_access)],
    db: DbSession,
) -> ContentEngagementResponse:
    data = await DashboardService(db).get_engagement(doctor_id)
    return ContentEngagementResponse.model_validate(data)


async def get_glance(
    db: DbSession,
    auth: Annotated[WorkspaceSelectAuth, Depends(require_workspace_select_auth)],
) -> GlanceApiResponse:
    async def _run(_: Any = None) -> dict[str, Any]:
        return await DashboardService(db).get_glance(
            auth.linqmd_user_id,
            workspace_id=auth.workspace_id,
            ws_user_id=auth.ws_user_id,
        )

    envelope = await _controller.execute_method(
        _run, None, success_msg=_MSG_GLANCE_GET, pass_payload=True
    )
    if envelope.get("status_code") != 200:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=envelope.get("msg") or "Glance failed",
        )
    return _controller.dashboard_response.glance_success(
        _MSG_GLANCE_GET, envelope["data"]
    )


async def sync_glance(
    db: DbSession,
    auth: Annotated[WorkspaceSelectAuth, Depends(require_workspace_select_auth)],
) -> GlanceApiResponse:
    try:
        async def _run(_: Any = None) -> dict[str, Any]:
            data = await DashboardService(db).sync_pending_glance(auth.authorization)
            await db.commit()
            return data

        envelope = await _controller.execute_method(
            _run, None, success_msg=_MSG_GLANCE_SYNC, pass_payload=True
        )
    except GlanceDashboardMissing as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PracticeHubPendingError as exc:
        if exc.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    if envelope.get("status_code") != 200:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=envelope.get("msg") or "Glance sync failed",
        )
    return _controller.dashboard_response.glance_success(
        _MSG_GLANCE_SYNC, envelope["data"]
    )


async def dashboard_webhook(
    payload: DashboardWebhookPayload,
    db: DbSession,
    auth: Annotated[WorkspaceSelectAuth, Depends(require_dashboard_webhook_auth)],
) -> GlanceApiResponse:
    schedule = [item.model_dump(mode="json") for item in payload.todays_schedule]
    try:
        async def _run(_: Any = None) -> dict[str, Any]:
            data = await DashboardService(db).process_dashboard_webhook(
                auth.authorization,
                appointments=payload.appointments,
                requests=payload.requests,
                todays_schedule=schedule,
            )
            await db.commit()
            return data

        envelope = await _controller.execute_method(
            _run, None, success_msg=_MSG_DASHBOARD_WEBHOOK, pass_payload=True
        )
    except GlanceDashboardMissing as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PracticeHubPendingError as exc:
        if exc.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    if envelope.get("status_code") != 200:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=envelope.get("msg") or "Dashboard webhook failed",
        )
    return _controller.dashboard_response.glance_success(
        _MSG_DASHBOARD_WEBHOOK, envelope["data"]
    )
