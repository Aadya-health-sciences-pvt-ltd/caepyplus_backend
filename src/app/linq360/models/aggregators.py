"""Content aggregator ORM models (public + linq360 schemas)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ...db.session import Base

# JSON works on both PostgreSQL (maps to JSON/JSONB via dialect) and SQLite.
from sqlalchemy import JSON


class BlogCommentsAggregator(Base):
    """Approved blog comment counts per doctor (public schema)."""

    __tablename__ = "blog_comments_aggregator"

    doctor_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PodcastCommentsAggregator(Base):
    """Approved podcast comment counts per doctor (public schema)."""

    __tablename__ = "podcast_comments_aggregator"

    doctor_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ReviewsPendingAggregator(Base):
    """Still-pending review inbox, keyed by Drupal uid (``linqmd_user_id``).

    CAEPY ``doctors.id`` is optional. A missing doctor or credentials row
    does not block this count.
    """

    __tablename__ = "reviews_pending_aggregator"

    linqmd_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pending_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    doctor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ReviewsSummaryAggregator(Base):
    """Published review rating summary per CAEPY doctor (public schema)."""

    __tablename__ = "reviews_summary_aggregator"

    doctor_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    pending_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    rating_sum: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    avg_rating: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    linqmd_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ContentSourceAggregator(Base):
    """Per-doctor per-source rollup (schema ``linq360``)."""

    __tablename__ = "content_source_aggregator"
    __table_args__ = (
        UniqueConstraint("doctor_id", "source", name="uq_content_source_aggregator_doctor_source"),
        {"schema": "linq360"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    avg_rating: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    rating_sum: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# Valid ``source`` values for ContentSourceAggregator
SOURCE_REVIEW = "review"
SOURCE_BLOG = "blog"
SOURCE_PODCAST = "podcast"
CONTENT_SOURCES = (SOURCE_REVIEW, SOURCE_BLOG, SOURCE_PODCAST)
