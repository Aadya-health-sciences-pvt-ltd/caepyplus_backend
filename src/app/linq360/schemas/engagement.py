"""Content engagement response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


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


class PendingCount(BaseModel):
    pending_count: int = 0


class GlanceContent(BaseModel):
    reviews: PendingCount = Field(default_factory=PendingCount)
    blog_comments: PendingCount = Field(default_factory=PendingCount)
    podcast_comments: PendingCount = Field(default_factory=PendingCount)


class GlanceResponse(BaseModel):
    """Today-at-a-glance content badge, keyed by Drupal uid."""

    linqmd_user_id: str
    content: GlanceContent


class GlanceSyncRequest(BaseModel):
    """Sync one Drupal uid from Practice Hub into CAEPY."""

    linqmd_user_id: str = Field(min_length=1)
