"""Linq360 content engagement API."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.rbac import get_current_user
from ...db.session import DbSession
from ...models.enums import UserRole
from ...models.user import User
from ...repositories.doctor_repository import DoctorRepository
from ..schemas.engagement import (
    ContentEngagementResponse,
    GlanceApiResponse,
    GlanceResponse,
)
from ..services.content_aggregator_service import (
    ContentAggregatorService,
    GlanceDashboardMissing,
)
from ..services.practice_hub_pending_client import PracticeHubPendingError
from .workspace_auth import WorkspaceSelectAuth, require_workspace_select_auth

router = APIRouter()
public_router = APIRouter()

_MSG_GLANCE_GET = "Glance retrieved successfully"
_MSG_GLANCE_SYNC = "Glance synced successfully"


async def require_doctor_engagement_access(
    doctor_id: int,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> int:
    """Allow admin/operation/content_creator, or the linked doctor."""
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


@router.get(
    "/doctors/{doctor_id}/content-engagement",
    response_model=ContentEngagementResponse,
)
async def get_content_engagement(
    doctor_id: Annotated[int, Depends(require_doctor_engagement_access)],
    db: DbSession,
) -> ContentEngagementResponse:
    """Return per-source content engagement counts for a doctor."""
    data = await ContentAggregatorService(db).get_engagement(doctor_id)
    return ContentEngagementResponse.model_validate(data)


@public_router.get("/glance", response_model=GlanceApiResponse)
async def get_glance(
    db: DbSession,
    auth: Annotated[WorkspaceSelectAuth, Depends(require_workspace_select_auth)],
) -> GlanceApiResponse:
    """Read stored pending inbox for the doctor on the workspace select token.

    Auth: ``Authorization: Bearer <workspace_select_access_token>``.
    No ``linqmd_user_id`` query param — uses ``appointment_doctor_id`` from the JWT.
    """
    data = await ContentAggregatorService(db).get_glance(
        auth.linqmd_user_id,
        workspace_id=auth.workspace_id,
    )
    return GlanceApiResponse(
        status_code=status.HTTP_200_OK,
        msg=_MSG_GLANCE_GET,
        data=GlanceResponse.model_validate(data),
    )


@public_router.post("/glance/sync", response_model=GlanceApiResponse)
async def sync_glance(
    db: DbSession,
    auth: Annotated[WorkspaceSelectAuth, Depends(require_workspace_select_auth)],
) -> GlanceApiResponse:
    """Pull LinQ360 pending counts with the workspace select token and store them.

    Auth: ``Authorization: Bearer <workspace_select_access_token>``.
    No request body / user_id. Calls Drupal ``GET …/pending-counts`` with the same
    Bearer token; stores under ``appointment_doctor_id``.
    """
    try:
        data = await ContentAggregatorService(db).sync_pending_glance(auth.authorization)
        await db.commit()
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
    return GlanceApiResponse(
        status_code=status.HTTP_200_OK,
        msg=_MSG_GLANCE_SYNC,
        data=GlanceResponse.model_validate(data),
    )
