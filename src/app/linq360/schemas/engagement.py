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
    content: GlanceContent
    appointments: int = 0
    requests: int = 0
    payments: dict[str, Any] = Field(default_factory=dict)
    todays_schedule: list[WorkspaceAppointmentItem] = Field(default_factory=list)


class GlanceApiResponse(BaseModel):
    status_code: int = 200
    msg: str
    data: GlanceResponse | None = None


class GlanceSyncRequest(BaseModel):
    model_config = {"extra": "ignore"}


class DashboardWebhookPayload(BaseModel):
    """Appointment-system webhook body.

    Identity from JWT. Optional ``event_type`` drives which dashboard sections
    refresh after debounce (default: appointments + requests snapshot).
    """

    event_type: str | None = None
    appointments: int = 0
    requests: int = 0
    todays_schedule: list[WorkspaceAppointmentItem] = Field(default_factory=list)
