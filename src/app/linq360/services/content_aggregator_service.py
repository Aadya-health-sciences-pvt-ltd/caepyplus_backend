"""Content aggregator service — approved rollups + pending todays_glance inbox."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ...models.blog import Blog, BlogComment
from ...models.enums import CommentStatus
from ..models.aggregators import (
    SOURCE_BLOG,
    SOURCE_PODCAST,
    SOURCE_REVIEW,
    BlogCommentsAggregator,
    ContentSourceAggregator,
    PodcastCommentsAggregator,
    ReviewsPendingAggregator,
    ReviewsSummaryAggregator,
)
from ..models.dashboard import WorkspaceDoctorDashboard


def blog_comment_delta(old_status: str, new_status: str) -> int:
    """Return +1 / -1 / 0 for approved-only comment counting."""
    was = old_status == CommentStatus.APPROVED.value
    now = new_status == CommentStatus.APPROVED.value
    if not was and now:
        return 1
    if was and not now:
        return -1
    return 0


def _floor_non_negative(value: int | Decimal) -> int | Decimal:
    if isinstance(value, Decimal):
        return value if value > 0 else Decimal("0")
    return value if value > 0 else 0


def _avg_rating(rating_sum: Decimal, review_count: int) -> Decimal | None:
    if review_count <= 0:
        return None
    return (rating_sum / Decimal(review_count)).quantize(Decimal("0.0001"))


def _glance_payload(
    linqmd_user_id: str, reviews: int, blogs: int, podcasts: int
) -> dict[str, Any]:
    return {
        "linqmd_user_id": linqmd_user_id,
        "content": {
            "reviews": {"pending_count": reviews},
            "blog_comments": {"pending_count": blogs},
            "podcast_comments": {"pending_count": podcasts},
        },
    }


def _default_glance() -> dict[str, Any]:
    """Pending moderation inbox shape (not approved engagement totals)."""
    return {
        "content": {
            "reviews": {"pending_count": 0},
            "blog_comments": {"pending_count": 0},
            "podcast_comments": {"pending_count": 0},
        },
        "appointments": {},
        "requests": {},
        "payments": {},
    }


class GlanceDashboardMissing(Exception):
    """No workspace_doctor_dashboard row exists for this Drupal uid."""

    def __init__(self, linqmd_user_id: str) -> None:
        super().__init__(
            "No linq360.workspace_doctor_dashboard row with user_id="
            f"{linqmd_user_id}. todays_glance can only be stored on that row."
        )
        self.linqmd_user_id = linqmd_user_id


def _pending_from_glance(glance: dict[str, Any] | None, key: str) -> int:
    content = (glance or {}).get("content") or {}
    block = content.get(key) or {}
    if not isinstance(block, dict):
        return 0
    try:
        number = int(block.get("pending_count") or 0)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


class ContentAggregatorService:
    """Adjust / rebuild content aggregators; pending inbox → todays_glance."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Adjust helpers (approved / published metrics)
    # ------------------------------------------------------------------

    async def adjust_blog_comments(self, doctor_id: int, delta: int) -> BlogCommentsAggregator:
        row = await self._get_or_create_blog(doctor_id)
        row.comment_count = int(_floor_non_negative(row.comment_count + delta))
        await self._upsert_main_comments(doctor_id, SOURCE_BLOG, row.comment_count)
        return row

    async def adjust_podcast_comments(
        self, doctor_id: int, delta: int
    ) -> PodcastCommentsAggregator:
        row = await self._get_or_create_podcast(doctor_id)
        row.comment_count = int(_floor_non_negative(row.comment_count + delta))
        await self._upsert_main_comments(doctor_id, SOURCE_PODCAST, row.comment_count)
        return row

    async def adjust_reviews(
        self,
        doctor_id: int,
        rating: float | Decimal,
        delta: int,
        linqmd_user_id: str | None = None,
    ) -> ReviewsSummaryAggregator:
        """Adjust published review metrics only — does not touch todays_glance."""
        row = await self._get_or_create_reviews(doctor_id)
        rating_dec = Decimal(str(rating))
        if delta > 0:
            row.review_count = int(_floor_non_negative(row.review_count + delta))
            row.rating_sum = Decimal(
                str(_floor_non_negative(Decimal(str(row.rating_sum)) + rating_dec * delta))
            )
        elif delta < 0:
            steps = abs(delta)
            row.review_count = int(_floor_non_negative(row.review_count - steps))
            row.rating_sum = Decimal(
                str(_floor_non_negative(Decimal(str(row.rating_sum)) - rating_dec * steps))
            )
        if row.review_count == 0:
            row.rating_sum = Decimal("0")
            row.avg_rating = None
        else:
            row.avg_rating = _avg_rating(Decimal(str(row.rating_sum)), row.review_count)
        if linqmd_user_id is not None:
            row.linqmd_user_id = linqmd_user_id
        await self._upsert_main_reviews(doctor_id, row)
        return row

    async def adjust_pending_reviews(
        self,
        linqmd_user_id: str,
        delta: int,
        doctor_id: int | None = None,
    ) -> ReviewsPendingAggregator:
        """Adjust pending review inbox keyed by Drupal uid and refresh glance.

        ``linqmd_user_id`` is required (Drupal ``reviews.user_id``).
        ``doctor_id`` is stored only when a CAEPY doctor already exists.
        Pending is saved even when no dashboard row exists.
        """
        uid = str(linqmd_user_id).strip()
        row = await self._get_or_create_pending_reviews(uid)
        row.pending_count = int(_floor_non_negative(row.pending_count + delta))
        if doctor_id is not None:
            row.doctor_id = doctor_id
        return row

    async def get_pending_reviews(self, linqmd_user_id: str) -> ReviewsPendingAggregator | None:
        """Read the pending inbox row by Drupal uid."""
        return await self.session.get(ReviewsPendingAggregator, str(linqmd_user_id).strip())

    async def get_glance(self, linqmd_user_id: str) -> dict[str, Any]:
        """Read pending counts from ``linq360.workspace_doctor_dashboard.todays_glance``.

        Does not call Drupal or MySQL. Missing dashboard row returns zeros.
        """
        uid = str(linqmd_user_id).strip()
        dash = await self._first_dashboard(uid)
        if dash is None:
            return _glance_payload(uid, 0, 0, 0)
        glance = dash.todays_glance or {}
        return _glance_payload(
            uid,
            _pending_from_glance(glance, "reviews"),
            _pending_from_glance(glance, "blog_comments"),
            _pending_from_glance(glance, "podcast_comments"),
        )

    async def upsert_pending_glance(
        self,
        linqmd_user_id: str,
        *,
        reviews_pending_count: int,
        blog_comments_pending_count: int,
        podcast_comments_pending_count: int,
    ) -> None:
        """Write pending counts into ``todays_glance`` for this Drupal uid."""
        uid = str(linqmd_user_id).strip()
        reviews = int(_floor_non_negative(reviews_pending_count))
        blogs = int(_floor_non_negative(blog_comments_pending_count))
        podcasts = int(_floor_non_negative(podcast_comments_pending_count))
        await self._refresh_todays_glance_content(uid, reviews, blogs, podcasts)

    async def sync_pending_glance(self, linqmd_user_id: str) -> dict[str, Any]:
        """GET Practice Hub pending counts and upsert the CAEPY row."""
        from .practice_hub_pending_client import fetch_pending_counts

        counts = await fetch_pending_counts(linqmd_user_id)
        await self.upsert_pending_glance(linqmd_user_id, **counts)
        return await self.get_glance(linqmd_user_id)

    # ------------------------------------------------------------------
    # Rebuild helpers
    # ------------------------------------------------------------------

    async def rebuild_blog_comments(self, doctor_id: int) -> BlogCommentsAggregator:
        result = await self.session.execute(
            select(func.count())
            .select_from(BlogComment)
            .join(Blog, BlogComment.blog_id == Blog.id)
            .where(
                Blog.doctor_id == doctor_id,
                BlogComment.status == CommentStatus.APPROVED.value,
            )
        )
        count = int(result.scalar_one() or 0)
        row = await self._get_or_create_blog(doctor_id)
        row.comment_count = count
        await self._upsert_main_comments(doctor_id, SOURCE_BLOG, count)
        return row

    async def rebuild_podcast_comments(self, doctor_id: int) -> PodcastCommentsAggregator:
        """No local podcast comments table yet — resync main from existing aggregator row."""
        row = await self._get_or_create_podcast(doctor_id)
        await self._upsert_main_comments(doctor_id, SOURCE_PODCAST, row.comment_count)
        return row

    async def rebuild_reviews(self, doctor_id: int) -> ReviewsSummaryAggregator:
        """Resync published review metrics only. Does not write todays_glance."""
        row = await self._get_or_create_reviews(doctor_id)
        if row.review_count == 0:
            row.rating_sum = Decimal("0")
            row.avg_rating = None
        else:
            row.avg_rating = _avg_rating(Decimal(str(row.rating_sum)), row.review_count)
        await self._upsert_main_reviews(doctor_id, row)
        return row

    async def rebuild_all(self, doctor_id: int) -> dict[str, Any]:
        blog = await self.rebuild_blog_comments(doctor_id)
        podcast = await self.rebuild_podcast_comments(doctor_id)
        reviews = await self.rebuild_reviews(doctor_id)
        return {
            "blog_comment_count": blog.comment_count,
            "podcast_comment_count": podcast.comment_count,
            "review_count": reviews.review_count,
            "avg_rating": float(reviews.avg_rating) if reviews.avg_rating is not None else None,
        }

    # ------------------------------------------------------------------
    # Engagement read (published metrics only)
    # ------------------------------------------------------------------

    async def get_engagement(self, doctor_id: int) -> dict[str, Any]:
        result = await self.session.execute(
            select(ContentSourceAggregator).where(ContentSourceAggregator.doctor_id == doctor_id)
        )
        rows = list(result.scalars().all())
        by_source = {r.source: r for r in rows}

        def _source_payload(source: str) -> dict[str, Any]:
            row = by_source.get(source)
            if row is None:
                base: dict[str, Any] = {"source": source, "item_count": 0}
                if source == SOURCE_REVIEW:
                    base["avg_rating"] = None
                    base["rating_sum"] = None
                return base
            payload: dict[str, Any] = {
                "source": source,
                "item_count": row.item_count,
            }
            if source == SOURCE_REVIEW:
                payload["avg_rating"] = float(row.avg_rating) if row.avg_rating is not None else None
                payload["rating_sum"] = float(row.rating_sum) if row.rating_sum is not None else None
            return payload

        sources = [
            _source_payload(SOURCE_REVIEW),
            _source_payload(SOURCE_BLOG),
            _source_payload(SOURCE_PODCAST),
        ]
        total = sum(s["item_count"] for s in sources)
        return {
            "doctor_id": doctor_id,
            "sources": sources,
            "total_item_count": total,
        }

    # ------------------------------------------------------------------
    # Internal: get-or-create / upsert / glance
    # ------------------------------------------------------------------

    async def _get_or_create_blog(self, doctor_id: int) -> BlogCommentsAggregator:
        row = await self.session.get(BlogCommentsAggregator, doctor_id)
        if row is None:
            row = BlogCommentsAggregator(doctor_id=doctor_id, comment_count=0)
            self.session.add(row)
            await self.session.flush()
        return row

    async def _get_or_create_podcast(self, doctor_id: int) -> PodcastCommentsAggregator:
        row = await self.session.get(PodcastCommentsAggregator, doctor_id)
        if row is None:
            row = PodcastCommentsAggregator(doctor_id=doctor_id, comment_count=0)
            self.session.add(row)
            await self.session.flush()
        return row

    async def _get_or_create_reviews(self, doctor_id: int) -> ReviewsSummaryAggregator:
        row = await self.session.get(ReviewsSummaryAggregator, doctor_id)
        if row is None:
            row = ReviewsSummaryAggregator(
                doctor_id=doctor_id,
                review_count=0,
                pending_count=0,
                rating_sum=Decimal("0"),
                avg_rating=None,
            )
            self.session.add(row)
            await self.session.flush()
        return row

    async def _get_or_create_main(self, doctor_id: int, source: str) -> ContentSourceAggregator:
        result = await self.session.execute(
            select(ContentSourceAggregator).where(
                ContentSourceAggregator.doctor_id == doctor_id,
                ContentSourceAggregator.source == source,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ContentSourceAggregator(
                doctor_id=doctor_id,
                source=source,
                item_count=0,
                metrics={},
            )
            self.session.add(row)
            await self.session.flush()
        return row

    async def _upsert_main_comments(self, doctor_id: int, source: str, item_count: int) -> None:
        main = await self._get_or_create_main(doctor_id, source)
        main.item_count = item_count
        main.avg_rating = None
        main.rating_sum = None

    async def _upsert_main_reviews(self, doctor_id: int, row: ReviewsSummaryAggregator) -> None:
        main = await self._get_or_create_main(doctor_id, SOURCE_REVIEW)
        main.item_count = row.review_count
        main.rating_sum = Decimal(str(row.rating_sum)) if row.review_count else None
        main.avg_rating = row.avg_rating

    async def _get_or_create_pending_reviews(self, linqmd_user_id: str) -> ReviewsPendingAggregator:
        row = await self.session.get(ReviewsPendingAggregator, linqmd_user_id)
        if row is None:
            row = ReviewsPendingAggregator(linqmd_user_id=linqmd_user_id, pending_count=0)
            self.session.add(row)
            await self.session.flush()
        return row

    async def _dashboards_for_uid(self, linqmd_user_id: str) -> list[WorkspaceDoctorDashboard]:
        if not linqmd_user_id.isdigit():
            return []
        result = await self.session.execute(
            select(WorkspaceDoctorDashboard)
            .where(WorkspaceDoctorDashboard.user_id == int(linqmd_user_id))
            .order_by(WorkspaceDoctorDashboard.appointment_id)
        )
        return list(result.scalars().all())

    async def _ensure_dashboard(self, linqmd_user_id: str) -> list[WorkspaceDoctorDashboard]:
        """Return dashboard rows for this Drupal uid, creating one when none exist."""
        if not linqmd_user_id.isdigit():
            raise GlanceDashboardMissing(linqmd_user_id)
        rows = await self._dashboards_for_uid(linqmd_user_id)
        if rows:
            return rows
        row = WorkspaceDoctorDashboard(
            workspace_id=0,
            user_id=int(linqmd_user_id),
            appointments_json={},
            todays_glance=_default_glance(),
        )
        self.session.add(row)
        await self.session.flush()
        return [row]

    async def _first_dashboard(self, linqmd_user_id: str) -> WorkspaceDoctorDashboard | None:
        rows = await self._dashboards_for_uid(linqmd_user_id)
        return rows[0] if rows else None

    async def _refresh_todays_glance_content(
        self,
        linqmd_user_id: str,
        reviews: int,
        blogs: int,
        podcasts: int,
    ) -> None:
        """Write pending counts into ``todays_glance`` where ``user_id`` is the Drupal uid.

        Creates one dashboard row when none exists so the JSON can be stored.
        """
        content = _glance_payload(linqmd_user_id, reviews, blogs, podcasts)["content"]
        dashboards = await self._ensure_dashboard(linqmd_user_id)
        for dash in dashboards:
            glance = dict(dash.todays_glance) if dash.todays_glance else _default_glance()
            glance.pop("messages", None)
            for key in ("appointments", "requests", "payments"):
                glance.setdefault(key, {})
            glance["content"] = content
            dash.todays_glance = glance
            flag_modified(dash, "todays_glance")
        await self.session.flush()
