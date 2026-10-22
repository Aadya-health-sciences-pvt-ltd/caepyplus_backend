"""Mirrored Drupal podcast comments for pending-status tracking."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.session import Base
from .enums import CommentStatus


class PodcastComment(Base):
    """Lightweight mirror of a Drupal podcast comment."""

    __tablename__ = "podcast_comments"

    comment_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    podcast_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    doctor_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=CommentStatus.PENDING.value,
        index=True,
    )
    parent_comment_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    @property
    def is_top_level(self) -> bool:
        return self.parent_comment_id is None
