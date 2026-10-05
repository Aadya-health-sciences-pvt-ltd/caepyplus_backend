"""Tests for ContentAggregatorService (adjust, floor, main upsert, glance)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.linq360.models.aggregators import (
    SOURCE_BLOG,
    BlogCommentsAggregator,
    ContentSourceAggregator,
    PodcastCommentsAggregator,
    ReviewsPendingAggregator,
    ReviewsSummaryAggregator,
)
from src.app.linq360.models.dashboard import WorkspaceDoctorDashboard
from src.app.linq360.services.content_aggregator_service import (
    ContentAggregatorService,
    blog_comment_delta,
)
from src.app.models.blog import Blog, BlogComment
from src.app.models.doctor import Doctor
from src.app.models.enums import CommentStatus


class TestBlogCommentDelta:
    def test_pending_to_approved(self) -> None:
        assert blog_comment_delta("pending", "approved") == 1

    def test_approved_to_rejected(self) -> None:
        assert blog_comment_delta("approved", "rejected") == -1

    def test_pending_to_rejected(self) -> None:
        assert blog_comment_delta("pending", "rejected") == 0

    def test_approved_to_pending(self) -> None:
        assert blog_comment_delta("approved", "pending") == -1

    def test_replied_never_counts(self) -> None:
        assert blog_comment_delta("pending", "replied") == 0
        assert blog_comment_delta("replied", "approved") == 1
        assert blog_comment_delta("approved", "replied") == -1


class TestAdjustBlogPodcast:
    async def test_blog_plus_minus_and_floor(self, db_session: AsyncSession) -> None:
        svc = ContentAggregatorService(db_session)
        await svc.adjust_blog_comments(10, 1)
        await svc.adjust_blog_comments(10, 1)
        row = await db_session.get(BlogCommentsAggregator, 10)
        assert row is not None
        assert row.comment_count == 2

        await svc.adjust_blog_comments(10, -5)
        assert row.comment_count == 0

        main = (
            await db_session.execute(
                select(ContentSourceAggregator).where(
                    ContentSourceAggregator.doctor_id == 10,
                    ContentSourceAggregator.source == SOURCE_BLOG,
                )
            )
        ).scalar_one()
        assert main.item_count == 0
        assert main.avg_rating is None

    async def test_podcast_adjust(self, db_session: AsyncSession) -> None:
        svc = ContentAggregatorService(db_session)
        await svc.adjust_podcast_comments(11, 3)
        row = await db_session.get(PodcastCommentsAggregator, 11)
        assert row is not None
        assert row.comment_count == 3
        await svc.adjust_podcast_comments(11, -1)
        assert row.comment_count == 2


class TestAdjustReviews:
    async def test_reviews_rating_sum_and_avg(self, db_session: AsyncSession) -> None:
        svc = ContentAggregatorService(db_session)
        await svc.adjust_reviews(20, 5, 1, linqmd_user_id="uid-20")
        await svc.adjust_reviews(20, 3, 1)
        row = await db_session.get(ReviewsSummaryAggregator, 20)
        assert row is not None
        assert row.review_count == 2
        assert float(row.rating_sum) == 8.0
        assert float(row.avg_rating) == 4.0
        assert row.linqmd_user_id == "uid-20"

        await svc.adjust_reviews(20, 5, -1)
        assert row.review_count == 1
        assert float(row.rating_sum) == 3.0
        assert float(row.avg_rating) == 3.0

        await svc.adjust_reviews(20, 3, -1)
        assert row.review_count == 0
        assert float(row.rating_sum) == 0.0
        assert row.avg_rating is None

    async def test_reviews_floor(self, db_session: AsyncSession) -> None:
        svc = ContentAggregatorService(db_session)
        await svc.adjust_reviews(21, 4, -1)
        row = await db_session.get(ReviewsSummaryAggregator, 21)
        assert row is not None
        assert row.review_count == 0
        assert float(row.rating_sum) == 0.0


class TestMainUpsertAndGlance:
    async def test_main_unique_per_source(self, db_session: AsyncSession) -> None:
        svc = ContentAggregatorService(db_session)
        await svc.adjust_blog_comments(30, 1)
        await svc.adjust_blog_comments(30, 1)
        count = (
            await db_session.execute(
                select(func.count())
                .select_from(ContentSourceAggregator)
                .where(
                    ContentSourceAggregator.doctor_id == 30,
                    ContentSourceAggregator.source == SOURCE_BLOG,
                )
            )
        ).scalar_one()
        assert count == 1

    async def test_approved_adjust_does_not_write_glance(self, db_session: AsyncSession) -> None:
        dash = WorkspaceDoctorDashboard(
            workspace_id=1,
            user_id=40,
            appointments_json={},
            todays_glance={},
        )
        db_session.add(dash)
        await db_session.flush()

        svc = ContentAggregatorService(db_session)
        await svc.adjust_blog_comments(40, 2)
        await svc.adjust_reviews(40, 5, 1)
        await db_session.refresh(dash)
        assert dash.todays_glance == {} or "reviews" not in (dash.todays_glance or {}).get(
            "content", {}
        )

    async def test_webhook_pending_does_not_write_glance(
        self, db_session: AsyncSession
    ) -> None:
        dash = WorkspaceDoctorDashboard(
            workspace_id=1,
            user_id=884,
            appointments_json={},
            todays_glance={},
        )
        db_session.add(dash)
        await db_session.flush()

        svc = ContentAggregatorService(db_session)
        await svc.adjust_pending_reviews("884", 1)
        await svc.adjust_pending_reviews("884", 1)
        await svc.adjust_pending_reviews("884", -10)
        row = await db_session.get(ReviewsPendingAggregator, "884")
        assert row is not None
        assert row.pending_count == 0
        await db_session.refresh(dash)
        assert dash.todays_glance == {} or "reviews" not in (dash.todays_glance or {}).get(
            "content", {}
        )

    async def test_stored_glance_row_and_dashboard(self, db_session: AsyncSession) -> None:
        dash = WorkspaceDoctorDashboard(
            workspace_id=1,
            user_id=884,
            appointments_json={},
            todays_glance={},
        )
        db_session.add(dash)
        await db_session.flush()

        svc = ContentAggregatorService(db_session)
        empty = await svc.get_glance("884")
        assert empty["content"]["reviews"]["pending_count"] == 0
        assert empty["content"]["blog_comments"]["pending_count"] == 0
        assert empty["content"]["podcast_comments"]["pending_count"] == 0

        await svc.upsert_pending_glance(
            "884",
            reviews_pending_count=2,
            blog_comments_pending_count=1,
            podcast_comments_pending_count=0,
        )

        glance = await svc.get_glance("884")
        assert glance["content"]["reviews"]["pending_count"] == 2
        assert glance["content"]["blog_comments"]["pending_count"] == 1
        assert glance["content"]["podcast_comments"]["pending_count"] == 0
        assert "appointments" not in glance

        await db_session.refresh(dash)
        content = dash.todays_glance["content"]
        assert content["reviews"]["pending_count"] == 2
        assert content["blog_comments"]["pending_count"] == 1
        assert "item_count" not in content["reviews"]
        assert "appointments" in dash.todays_glance

    async def test_upsert_creates_dashboard_row_when_missing(
        self, db_session: AsyncSession
    ) -> None:
        svc = ContentAggregatorService(db_session)
        await svc.upsert_pending_glance(
            "884",
            reviews_pending_count=1,
            blog_comments_pending_count=0,
            podcast_comments_pending_count=0,
        )
        glance = await svc.get_glance("884")
        assert glance["content"]["reviews"]["pending_count"] == 1
        result = await db_session.execute(
            select(WorkspaceDoctorDashboard).where(WorkspaceDoctorDashboard.user_id == 884)
        )
        row = result.scalar_one()
        assert row.todays_glance["content"]["reviews"]["pending_count"] == 1

    async def test_pending_saved_without_dashboard_or_doctor(
        self, db_session: AsyncSession
    ) -> None:
        svc = ContentAggregatorService(db_session)
        row = await svc.adjust_pending_reviews("884", 1)
        assert row.pending_count == 1
        assert row.doctor_id is None
        loaded = await svc.get_pending_reviews("884")
        assert loaded is not None
        assert loaded.pending_count == 1

class TestRebuildBlog:
    async def test_rebuild_from_approved_comments(self, db_session: AsyncSession) -> None:
        doctor = Doctor(full_name="Dr Test")
        db_session.add(doctor)
        await db_session.flush()

        blog = Blog(doctor_id=doctor.id, title="T", status="published")
        db_session.add(blog)
        await db_session.flush()

        for status in (
            CommentStatus.APPROVED.value,
            CommentStatus.APPROVED.value,
            CommentStatus.PENDING.value,
            CommentStatus.REJECTED.value,
        ):
            db_session.add(
                BlogComment(
                    blog_id=blog.id,
                    author_name="A",
                    content="c",
                    status=status,
                )
            )
        await db_session.flush()

        svc = ContentAggregatorService(db_session)
        row = await svc.rebuild_blog_comments(doctor.id)
        assert row.comment_count == 2

        engagement = await svc.get_engagement(doctor.id)
        assert engagement["total_item_count"] == 2
        blog_src = next(s for s in engagement["sources"] if s["source"] == SOURCE_BLOG)
        assert blog_src["item_count"] == 2
