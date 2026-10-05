"""Linq360 content engagement API."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...core.rbac import get_current_user
from ...db.session import DbSession
from ...models.enums import UserRole
from ...models.user import User
from ...repositories.doctor_repository import DoctorRepository
from ..schemas.engagement import ContentEngagementResponse, GlanceResponse, GlanceSyncRequest
from ..services.content_aggregator_service import (
    ContentAggregatorService,
    GlanceDashboardMissing,
)
from ..services.practice_hub_pending_client import PracticeHubPendingError

router = APIRouter()
public_router = APIRouter()


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


@public_router.get("/glance", response_model=GlanceResponse)
async def get_glance(
    db: DbSession,
    linqmd_user_id: Annotated[str, Query(min_length=1)],
) -> GlanceResponse:
    """Pending content badge for a Drupal uid.

    Public. Reads ``linq360.workspace_doctor_dashboard.todays_glance`` only.
    No Drupal MySQL, no doctor JWT. Missing dashboard row returns all three counts as 0.
    """
    data = await ContentAggregatorService(db).get_glance(linqmd_user_id.strip())
    return GlanceResponse.model_validate(data)


@public_router.post("/glance/sync", response_model=GlanceResponse)
async def sync_glance(body: GlanceSyncRequest, db: DbSession) -> GlanceResponse:
    """Pull Practice Hub pending counts for one Drupal uid and store them.

    Public. No doctor JWT. ``linqmd_user_id`` is the Drupal uid.
    """
    try:
        data = await ContentAggregatorService(db).sync_pending_glance(body.linqmd_user_id.strip())
    except GlanceDashboardMissing as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PracticeHubPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return GlanceResponse.model_validate(data)
