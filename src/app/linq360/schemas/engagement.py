"""Engagement / glance schemas (owned by dashboard fields; kept for import paths)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .dashboard import WorkspaceAppointmentItem


class ContentSourceEngagement(BaseModel):
    source: str
    item_count: int = 0
    avg_rating: float | None = None
    rating_sum: float | None = None


class ContentEngagementResponse(BaseModel):
    doctor_id: int
    sources: list[ContentSourceEngagement] = Field(default_factory=list)
    total_item_count: int = 0


class ReviewsPending(BaseModel):
    pending_count: int = 0
    review_id: list[int] = Field(default_factory=list)


class BlogCommentsPending(BaseModel):
    pending_count: int = 0
    comment_id: list[int] = Field(default_factory=list)
    blog_id: list[int] = Field(default_factory=list)


class PodcastCommentsPending(BaseModel):
    pending_count: int = 0
    comment_id: list[int] = Field(default_factory=list)
    podcast_id: list[int] = Field(default_factory=list)


class GlanceContent(BaseModel):
    reviews: ReviewsPending = Field(default_factory=ReviewsPending)
    blog_comments: BlogCommentsPending = Field(default_factory=BlogCommentsPending)
    podcast_comments: PodcastCommentsPending = Field(default_factory=PodcastCommentsPending)
    total_pending_counts: int = 0


class GlanceResponse(BaseModel):
    """Legacy merged glance (tests / WS snapshots may still use this shape)."""

    content: GlanceContent = Field(default_factory=GlanceContent)
    appointments: int = 0
    requests: int = 0
    payments: dict[str, Any] = Field(default_factory=dict)
    todays_schedule: list[WorkspaceAppointmentItem] = Field(default_factory=list)


class ContentGlanceData(BaseModel):
    """GET /glance/content + POST /glance/sync response data."""

    content: GlanceContent = Field(default_factory=GlanceContent)
    payments: dict[str, Any] = Field(default_factory=dict)


class AppointmentsGlanceData(BaseModel):
    """GET /glance/appointments + webhook response data."""

    appointments: int = 0
    requests: int = 0
    todays_schedule: list[WorkspaceAppointmentItem] = Field(default_factory=list)


class GlanceApiResponse(BaseModel):
    status_code: int = 200
    msg: str
    data: GlanceResponse | ContentGlanceData | AppointmentsGlanceData | None = None


class ContentGlanceApiResponse(BaseModel):
    status_code: int = 200
    msg: str
    data: ContentGlanceData | None = None


class AppointmentsGlanceApiResponse(BaseModel):
    status_code: int = 200
    msg: str
    data: AppointmentsGlanceData | None = None


class GlanceSyncRequest(BaseModel):
    model_config = {"extra": "ignore"}


class DashboardWebhookPayload(BaseModel):
    """Appointment-system webhook body (no Bearer).

    Identity is required in the body. Optional ``event_type`` drives which
    dashboard sections refresh after debounce.
    """

    ph_user_id: int = Field(..., gt=0)
    ws_user_id: int = Field(..., gt=0)
    workspace_id: int = Field(..., gt=0)
    event_type: str | None = None
    appointments: int = 0
    requests: int = 0
    todays_schedule: list[WorkspaceAppointmentItem] = Field(default_factory=list)
