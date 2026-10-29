"""Content aggregator service — approved rollups + pending counters / glance."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ...models.blog import Blog, BlogComment
from ...models.enums import CommentStatus, ReviewStatus
from ...models.podcast_comment import PodcastComment
from ...models.review import Review
from ...repositories.linqmd_credentials_repository import LinqmdCredentialsRepository
from ..models.aggregators import (
    SOURCE_BLOG,
    SOURCE_PODCAST,
    SOURCE_REVIEW,
    BlogCommentStats,
    BlogCommentsAggregator,
    ContentSourceAggregator,
    PodcastCommentStats,
    PodcastCommentsAggregator,
    ReviewsAggregator,
    ReviewsPendingAggregator,
    ReviewsSummaryAggregator,
)
from ..dashboard.dashboard_content import content_block, payload_from_stored_content
from ..dashboard.dashboard_repository import (
    DashboardRepository,
    GlanceDashboardMissing,
)
from ..dashboard.config.dashboard_service import DashboardService
from ..models.dashboard import DoctorDashboard, WorkspaceDoctorDashboard
from .practice_hub_pending_client import (
    PENDING_SOURCES,
    non_negative_int,
    parse_source_block,
    pending_count_from_block,
)


def blog_comment_delta(old_status: str, new_status: str) -> int:
    """Return +1 / -1 / 0 for approved-only comment counting."""
    was = old_status == CommentStatus.APPROVED.value
    now = new_status == CommentStatus.APPROVED.value
    if not was and now:
        return 1
    if was and not now:
        return -1
    return 0


def pending_status_delta(
    old_status: str | None,
    new_status: str,
    *,
    is_top_level: bool,
) -> int:
    """Return +1 / -1 / 0 when a top-level row enters or leaves pending.

    Replies never affect pending counters.
    """
    if not is_top_level:
        return 0
    was = (old_status or "") == CommentStatus.PENDING.value
    now = new_status == CommentStatus.PENDING.value
    if not was and now:
        return 1
    if was and not now:
        return -1
    return 0


def _floor_non_negative(value: int | Decimal) -> int | Decimal:
    if isinstance(value, Decimal):
        return value if value > 0 else Decimal("0")
    return non_negative_int(value)


_COMMENT_AGGREGATORS = {
    SOURCE_BLOG: BlogCommentsAggregator,
    SOURCE_PODCAST: PodcastCommentsAggregator,
}


def _avg_rating(rating_sum: Decimal, review_count: int) -> Decimal | None:
    if review_count <= 0:
        return None
    return (rating_sum / Decimal(review_count)).quantize(Decimal("0.0001"))


def _payload_from_stored_content(existing: dict[str, Any] | None) -> dict[str, Any]:
    return payload_from_stored_content(existing)


def _counts_from_glance(existing: dict[str, Any] | None) -> dict[str, int]:
    from ..dashboard.dashboard_content import counts_from_glance

    return counts_from_glance(existing)


def _content_block(payload: dict[str, Any]) -> dict[str, Any]:
    return content_block(payload)


# Re-export for existing imports.
__all__ = [
    "ContentAggregatorService",
    "GlanceDashboardMissing",
    "blog_comment_delta",
    "pending_status_delta",
]


class ContentAggregatorService:
    """Adjust / rebuild content aggregators; pending inbox → todays_glance."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Adjust helpers (approved / published metrics)
    # ------------------------------------------------------------------

    async def adjust_blog_comments(self, doctor_id: int, delta: int) -> BlogCommentsAggregator:
        return await self._adjust_comments(doctor_id, SOURCE_BLOG, delta)

    async def adjust_podcast_comments(
        self, doctor_id: int, delta: int
    ) -> PodcastCommentsAggregator:
        return await self._adjust_comments(doctor_id, SOURCE_PODCAST, delta)

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
        if delta != 0:
            row.review_count = int(_floor_non_negative(row.review_count + delta))
            row.rating_sum = Decimal(
                str(_floor_non_negative(Decimal(str(row.rating_sum)) + rating_dec * delta))
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
        """Legacy webhook counter. Prefer ``adjust_reviews_aggregator_pending``."""
        uid = str(linqmd_user_id).strip()
        row = await self._get_or_create_pending_reviews(uid)
        row.pending_count = non_negative_int(row.pending_count + delta)
        if doctor_id is not None:
            row.doctor_id = doctor_id
        return row

    async def get_pending_reviews(self, linqmd_user_id: str) -> ReviewsPendingAggregator | None:
        """Read the legacy pending inbox row by Drupal uid."""
        return await self.session.get(ReviewsPendingAggregator, str(linqmd_user_id).strip())

    # ------------------------------------------------------------------
    # Pending counters (reviews_aggregator / *_comment_stats)
    # ------------------------------------------------------------------

    async def adjust_reviews_aggregator_pending(
        self,
        user_id: str,
        delta: int,
        doctor_id: int | None = None,
        *,
        refresh_glance: bool = False,
    ) -> ReviewsAggregator:
        """Apply ±1 to reviews_aggregator, or seed from COUNT when missing.

        Caller must flush local ``reviews`` rows before calling so the seed
        COUNT includes the current transition. When seeding, ``delta`` is not
        applied on top of the COUNT.
        """
        uid = str(user_id).strip()
        row = await self.session.get(ReviewsAggregator, uid)
        if row is None:
            count = await self._count_top_level_pending_reviews(uid)
            # Seed from COUNT when local reviews exist (includes the flushed row).
            # If there is no mirror yet, use a non-negative delta as the initial value.
            if count > 0:
                initial = count
            else:
                initial = non_negative_int(delta)
            row = ReviewsAggregator(
                user_id=uid,
                rating=1,
                rating_count=0,
                pending_count=initial,
                doctor_id=doctor_id,
            )
            self.session.add(row)
            await self.session.flush()
        else:
            if delta != 0:
                row.pending_count = non_negative_int(row.pending_count + delta)
            if doctor_id is not None:
                row.doctor_id = doctor_id
            await self.session.flush()
        if refresh_glance:
            await self.refresh_glance_from_counters(linqmd_user_id=uid, doctor_id=doctor_id)
        return row

    async def adjust_blog_comment_stats_pending(
        self,
        blog_id: int,
        doctor_id: int,
        delta: int,
        *,
        refresh_glance: bool = False,
    ) -> BlogCommentStats | None:
        """Apply ±1 to blog_comment_stats for (blog_id, doctor_id). Floor at 0."""
        if delta == 0:
            return await self._get_blog_comment_stats(blog_id, doctor_id)
        row = await self._get_or_create_blog_comment_stats(blog_id, doctor_id)
        row.pending_count = non_negative_int(row.pending_count + delta)
        await self.session.flush()
        if refresh_glance:
            await self.refresh_glance_from_counters(doctor_id=doctor_id)
        return row

    async def adjust_podcast_comment_stats_pending(
        self,
        podcast_id: str,
        doctor_id: int,
        delta: int,
        *,
        refresh_glance: bool = False,
    ) -> PodcastCommentStats | None:
        """Apply ±1 to podcast_comment_stats for (podcast_id, doctor_id). Floor at 0."""
        if delta == 0:
            return await self._get_podcast_comment_stats(str(podcast_id), doctor_id)
        row = await self._get_or_create_podcast_comment_stats(str(podcast_id), doctor_id)
        row.pending_count = non_negative_int(row.pending_count + delta)
        await self.session.flush()
        if refresh_glance:
            await self.refresh_glance_from_counters(doctor_id=doctor_id)
        return row

    async def sum_blog_pending(self, doctor_id: int) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(BlogCommentStats.pending_count), 0)).where(
                BlogCommentStats.doctor_id == doctor_id
            )
        )
        return non_negative_int(result.scalar_one())

    async def sum_podcast_pending(self, doctor_id: int) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(PodcastCommentStats.pending_count), 0)).where(
                PodcastCommentStats.doctor_id == doctor_id
            )
        )
        return non_negative_int(result.scalar_one())

    async def local_pending_counts(
        self,
        *,
        linqmd_user_id: str | None = None,
        doctor_id: int | None = None,
    ) -> dict[str, int]:
        """Build the three pending counts from stored counter tables."""
        uid, resolved_doctor_id = await self._resolve_identity(linqmd_user_id, doctor_id)
        reviews = 0
        if uid:
            row = await self.session.get(ReviewsAggregator, uid)
            reviews = non_negative_int(row.pending_count if row is not None else 0)
        blog = 0
        podcast = 0
        if resolved_doctor_id is not None:
            blog = await self.sum_blog_pending(resolved_doctor_id)
            podcast = await self.sum_podcast_pending(resolved_doctor_id)
        return {
            "reviews": reviews,
            "blog_comments": blog,
            "podcast_comments": podcast,
        }

    async def refresh_glance_from_counters(
        self,
        *,
        linqmd_user_id: str | None = None,
        doctor_id: int | None = None,
    ) -> None:
        """Write todays_glance from local counters. Skips when Drupal uid unknown."""
        uid, resolved_doctor_id = await self._resolve_identity(linqmd_user_id, doctor_id)
        if not uid:
            return
        counts = await self.local_pending_counts(
            linqmd_user_id=uid, doctor_id=resolved_doctor_id
        )
        try:
            await self._refresh_todays_glance_content(uid, counts)
        except GlanceDashboardMissing:
            # Non-numeric uid cannot store glance; counters still persist.
            return

    async def get_glance(
        self,
        linqmd_user_id: str,
        *,
        workspace_id: int | None = None,
        ws_user_id: int | None = None,
    ) -> dict[str, Any]:
        """Delegate to DashboardService (FAQ layering)."""
        return await DashboardService(self.session).get_glance(
            linqmd_user_id,
            workspace_id=workspace_id,
            ws_user_id=ws_user_id,
        )

    async def upsert_pending_glance(
        self,
        linqmd_user_id: str,
        payload: dict[str, Any],
        *,
        workspace_id: int | None = None,
        ws_user_id: int | None = None,
    ) -> None:
        await DashboardService(self.session).upsert_pending_glance(
            linqmd_user_id,
            payload,
            workspace_id=workspace_id,
            ws_user_id=ws_user_id,
        )

    async def sync_pending_glance(self, workspace_access_token: str) -> dict[str, Any]:
        return await DashboardService(self.session).sync_pending_glance(
            workspace_access_token
        )

    async def upsert_workspace_schedule(
        self,
        *,
        ph_user_id: int,
        workspace_id: int,
        ws_user_id: int | None = None,
        appointments: int = 0,
        requests: int = 0,
        todays_schedule: list[dict[str, Any]] | None = None,
    ) -> WorkspaceDoctorDashboard:
        return await DashboardService(self.session).upsert_workspace_schedule(
            ph_user_id=ph_user_id,
            workspace_id=workspace_id,
            ws_user_id=ws_user_id,
            appointments=appointments,
            requests=requests,
            todays_schedule=todays_schedule,
        )

    async def process_dashboard_webhook(
        self,
        workspace_access_token: str,
        *,
        appointments: int = 0,
        requests: int = 0,
        todays_schedule: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return await DashboardService(self.session).process_dashboard_webhook(
            workspace_access_token,
            appointments=appointments,
            requests=requests,
            todays_schedule=todays_schedule,
        )

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
        row = await self._get_or_create_comments(doctor_id, SOURCE_BLOG)
        row.comment_count = count
        await self._upsert_main_comments(doctor_id, SOURCE_BLOG, count)
        return row

    async def rebuild_podcast_comments(self, doctor_id: int) -> PodcastCommentsAggregator:
        """Resync main from approved podcast_comments mirror + aggregator row."""
        result = await self.session.execute(
            select(func.count())
            .select_from(PodcastComment)
            .where(
                PodcastComment.doctor_id == doctor_id,
                PodcastComment.status == CommentStatus.APPROVED.value,
            )
        )
        count = int(result.scalar_one() or 0)
        row = await self._get_or_create_comments(doctor_id, SOURCE_PODCAST)
        row.comment_count = count
        await self._upsert_main_comments(doctor_id, SOURCE_PODCAST, count)
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

    async def _resolve_identity(
        self,
        linqmd_user_id: str | None,
        doctor_id: int | None,
    ) -> tuple[str | None, int | None]:
        uid = str(linqmd_user_id).strip() if linqmd_user_id else None
        resolved_doctor = doctor_id
        creds_repo = LinqmdCredentialsRepository(self.session)
        if uid and resolved_doctor is None:
            creds = await creds_repo.get_by_linqmd_user_id(uid)
            if creds is not None:
                resolved_doctor = int(creds.doctor_id)
        if resolved_doctor is not None and not uid:
            creds = await creds_repo.get_by_doctor_id(int(resolved_doctor))
            if creds is not None and creds.linqmd_user_id:
                uid = str(creds.linqmd_user_id).strip()
        return uid, resolved_doctor

    async def _count_top_level_pending_reviews(self, user_id: str) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Review)
            .where(
                Review.user_id == user_id,
                Review.status == ReviewStatus.PENDING.value,
                Review.parent_review_id.is_(None),
            )
        )
        return int(result.scalar_one() or 0)

    async def _get_blog_comment_stats(
        self, blog_id: int, doctor_id: int
    ) -> BlogCommentStats | None:
        result = await self.session.execute(
            select(BlogCommentStats).where(
                BlogCommentStats.blog_id == blog_id,
                BlogCommentStats.doctor_id == doctor_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_or_create_blog_comment_stats(
        self, blog_id: int, doctor_id: int
    ) -> BlogCommentStats:
        row = await self._get_blog_comment_stats(blog_id, doctor_id)
        if row is None:
            row = BlogCommentStats(blog_id=blog_id, doctor_id=doctor_id, pending_count=0)
            self.session.add(row)
            await self.session.flush()
        return row

    async def _get_podcast_comment_stats(
        self, podcast_id: str, doctor_id: int
    ) -> PodcastCommentStats | None:
        result = await self.session.execute(
            select(PodcastCommentStats).where(
                PodcastCommentStats.podcast_id == podcast_id,
                PodcastCommentStats.doctor_id == doctor_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_or_create_podcast_comment_stats(
        self, podcast_id: str, doctor_id: int
    ) -> PodcastCommentStats:
        row = await self._get_podcast_comment_stats(podcast_id, doctor_id)
        if row is None:
            row = PodcastCommentStats(
                podcast_id=podcast_id, doctor_id=doctor_id, pending_count=0
            )
            self.session.add(row)
            await self.session.flush()
        return row

    async def _get_or_create_row(self, model: type[Any], key: Any, factory: Any) -> Any:
        row = await self.session.get(model, key)
        if row is None:
            row = factory()
            self.session.add(row)
            await self.session.flush()
        return row

    async def _get_or_create_comments(self, doctor_id: int, source: str) -> Any:
        model = _COMMENT_AGGREGATORS[source]
        return await self._get_or_create_row(
            model,
            doctor_id,
            lambda: model(doctor_id=doctor_id, comment_count=0),
        )

    async def _adjust_comments(self, doctor_id: int, source: str, delta: int) -> Any:
        row = await self._get_or_create_comments(doctor_id, source)
        row.comment_count = non_negative_int(row.comment_count + delta)
        await self._upsert_main_comments(doctor_id, source, row.comment_count)
        return row

    async def _get_or_create_reviews(self, doctor_id: int) -> ReviewsSummaryAggregator:
        return await self._get_or_create_row(
            ReviewsSummaryAggregator,
            doctor_id,
            lambda: ReviewsSummaryAggregator(
                doctor_id=doctor_id,
                review_count=0,
                pending_count=0,
                rating_sum=Decimal("0"),
                avg_rating=None,
            ),
        )

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
        return await self._get_or_create_row(
            ReviewsPendingAggregator,
            linqmd_user_id,
            lambda: ReviewsPendingAggregator(linqmd_user_id=linqmd_user_id, pending_count=0),
        )

    async def _get_workspace_dashboard(
        self,
        linqmd_user_id: str,
        workspace_id: int,
        *,
        ws_user_id: int | None = None,
    ) -> WorkspaceDoctorDashboard | None:
        return await DashboardRepository(self.session).get_workspace_dashboard(
            linqmd_user_id, workspace_id, ws_user_id=ws_user_id
        )

    async def _get_doctor_dashboard(self, linqmd_user_id: str) -> DoctorDashboard | None:
        return await DashboardRepository(self.session).get_doctor_dashboard(
            linqmd_user_id
        )

    async def _ensure_workspace_dashboard(
        self,
        linqmd_user_id: str,
        *,
        workspace_id: int | None = None,
        ws_user_id: int | None = None,
    ) -> WorkspaceDoctorDashboard:
        return await DashboardRepository(self.session).ensure_workspace_dashboard(
            linqmd_user_id,
            workspace_id=workspace_id,
            ws_user_id=ws_user_id,
        )

    async def _ensure_doctor_dashboard(
        self,
        linqmd_user_id: str,
        *,
        ws_user_id: int | None = None,
    ) -> DoctorDashboard:
        return await DashboardRepository(self.session).ensure_doctor_dashboard(
            linqmd_user_id, ws_user_id=ws_user_id
        )

    async def _refresh_todays_glance_content(
        self,
        linqmd_user_id: str,
        payload: dict[str, Any],
        *,
        workspace_id: int | None = None,
        ws_user_id: int | None = None,
    ) -> None:
        await DashboardService(self.session).upsert_pending_glance(
            linqmd_user_id,
            payload,
            workspace_id=workspace_id,
            ws_user_id=ws_user_id,
        )
