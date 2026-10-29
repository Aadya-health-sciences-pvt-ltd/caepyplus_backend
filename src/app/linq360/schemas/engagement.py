"""Content engagement response schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .dashboard import WorkspaceAppointmentItem


class ContentSourceEngagement(BaseModel):
    """Per-source engagement rollup."""

    source: str
    item_count: int = 0
    avg_rating: float | None = None
    rating_sum: float | None = None


class ContentEngagementResponse(BaseModel):
    """Doctor content engagement across review / blog / podcast."""

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
    """Today-at-a-glance payload under the API envelope ``data``.

    Dashboard badges: ``appointments`` / ``requests`` are integer counts.
    Patient details: ``todays_schedule`` array.
    """

    content: GlanceContent
    appointments: int = 0
    requests: int = 0
    payments: dict[str, Any] = Field(default_factory=dict)
    todays_schedule: list[WorkspaceAppointmentItem] = Field(default_factory=list)


class GlanceApiResponse(BaseModel):
    """HTTP envelope for glance GET / sync."""

    status_code: int = 200
    msg: str
    data: GlanceResponse


class GlanceSyncRequest(BaseModel):
    """Optional body for glance sync (unused; doctor comes from Bearer token)."""

    model_config = {"extra": "ignore"}


class DashboardWebhookPayload(BaseModel):
    """Appointment-system webhook body for workspace schedule + badge counts."""

    ph_user_id: int
    workspace_id: int
    ws_user_id: int | None = None
    appointments: int = 0
    requests: int = 0
    todays_schedule: list[WorkspaceAppointmentItem] = Field(default_factory=list)
