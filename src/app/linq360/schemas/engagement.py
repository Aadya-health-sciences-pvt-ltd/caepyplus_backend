"""Content engagement response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .dashboard import AppointmentJsonDocument


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
    """Today-at-a-glance. Same shape for sync and get.

    ``appointments`` matches ``appointment_json`` / ``AppointmentJsonDocument``.
    """

    content: GlanceContent
    appointments: AppointmentJsonDocument = Field(
        default_factory=AppointmentJsonDocument.empty
    )
    requests: dict = Field(default_factory=dict)
    payments: dict = Field(default_factory=dict)


class GlanceSyncRequest(BaseModel):
    """Optional body for glance sync (unused; doctor comes from Bearer token)."""

    model_config = {"extra": "ignore"}
