"""Mirrored Drupal reviews for pending-status and aggregator seeding."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.session import Base
from .enums import ReviewStatus


class Review(Base):
    """Lightweight mirror of a Drupal review (status + parent for pending rules)."""

    __tablename__ = "reviews"

    review_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ReviewStatus.PENDING.value,
        index=True,
    )
    parent_review_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    doctor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    @property
    def is_top_level(self) -> bool:
        return self.parent_review_id is None
