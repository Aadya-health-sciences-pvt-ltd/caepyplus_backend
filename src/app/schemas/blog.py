"""Pydantic schemas for the Blog Studio and Comment Moderation APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ConfigDict

from ..models.enums import BlogStatus, CommentStatus, CommentAuthorType


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------


class BlogKeywordResponse(BaseModel):
    """Keyword representation."""
    id: int
    keyword: str

    model_config = ConfigDict(from_attributes=True)


class BlogKeywordCreate(BaseModel):
    """Payload to add a keyword."""
    keyword: str = Field(..., max_length=100)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


class BlogCommentResponse(BaseModel):
    """Full representation of a comment."""
    id: int
    blog_id: int
    drupal_comment_id: str | None = None
    author_name: str
    author_type: CommentAuthorType
    content: str
    status: CommentStatus
    ai_insight: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CommentStatusUpdate(BaseModel):
    """Payload to update Comment Status (Approve/Reject)."""
    status: CommentStatus


# ---------------------------------------------------------------------------
# Blogs Core
# ---------------------------------------------------------------------------


class BlogResponse(BaseModel):
    """Full representation of a Blog."""
    id: int
    doctor_id: int
    title: str | None = None
    subtitle: str | None = None
    opening_quote: str | None = None
    content: str | None = None
    status: BlogStatus
    estimated_read_time: int | None = None
    drupal_node_id: str | None = None
    seo_schema_markup: dict[str, Any] | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    keywords: list[BlogKeywordResponse] = []
    
    # We might not need all comments instantly when loading a blog, 
    # but for simplicity, we include them if requested.
    # comments: list[BlogCommentResponse] = []

    model_config = ConfigDict(from_attributes=True)


class BlogCreate(BaseModel):
    """Payload to create a new draft blog."""
    title: str | None = Field(None, max_length=255)


class BlogUpdate(BaseModel):
    """Payload to update an existing blog draft."""
    title: str | None = Field(None, max_length=255)
    subtitle: str | None = Field(None, max_length=500)
    opening_quote: str | None = None
    content: str | None = None
    keywords: list[str] | None = None


class BlogPublishConfig(BaseModel):
    """Payload for publishing a blog."""
    push_to_practice_hub: bool = True
    share_to_linkedin: bool = False
    share_to_instagram: bool = False


# ---------------------------------------------------------------------------
# AI Insights (Stubs)
# ---------------------------------------------------------------------------


class AITopicCard(BaseModel):
    """A topic recommended by AI for Step 1."""
    tag: str
    title: str
    reasoning: str


class AITopicsResponse(BaseModel):
    topics: list[AITopicCard]


class AIKeywordSuggestionResponse(BaseModel):
    keywords: list[str]


class AIBlogContentGenerateRequest(BaseModel):
    """Payload to generate AI content for a blog."""
    topic: str
    keywords: list[str]


class AIBlogContentResponse(BaseModel):
    """Generated content response from AI."""
    subtitle: str
    opening_quote: str
    content: str


# ---------------------------------------------------------------------------
# Drupal Webhooks (Stubs)
# ---------------------------------------------------------------------------


class DrupalCommentWebhookPayload(BaseModel):
    """Incoming payload from Drupal when a comment is made."""
    drupal_comment_id: str
    drupal_node_id: str
    author_name: str
    content: str
