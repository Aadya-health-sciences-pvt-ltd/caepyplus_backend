"""Tests for ContentAggregatorService (adjust, floor, main upsert, glance)."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.linq360.models.aggregators import (
    SOURCE_BLOG,
    BlogCommentStats,
    BlogCommentsAggregator,
    ContentSourceAggregator,
    PodcastCommentStats,
    PodcastCommentsAggregator,
    ReviewsAggregator,
    ReviewsPendingAggregator,
    ReviewsSummaryAggregator,
)
from src.app.linq360.models.dashboard import DoctorDashboard, WorkspaceDoctorDashboard
from src.app.linq360.services.content_aggregator_service import (
    ContentAggregatorService,
    blog_comment_delta,
    pending_status_delta,
)
from src.app.models.blog import Blog, BlogComment
from src.app.models.doctor import Doctor
from src.app.models.enums import CommentStatus, ReviewStatus
from src.app.models.review import Review


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


class TestPendingStatusDelta:
    def test_enter_and_leave_pending(self) -> None:
        assert pending_status_delta(None, "pending", is_top_level=True) == 1
        assert pending_status_delta("pending", "approved", is_top_level=True) == -1
        assert pending_status_delta("pending", "flagged", is_top_level=True) == -1
        assert pending_status_delta("pending", "rejected", is_top_level=True) == -1

    def test_replies_ignored(self) -> None:
        assert pending_status_delta(None, "pending", is_top_level=False) == 0
        assert pending_status_delta("pending", "approved", is_top_level=False) == 0


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
        doctor = DoctorDashboard(ph_user_id=40, todays_glance={})
        workspace = WorkspaceDoctorDashboard(
            workspace_id=1,
            ph_user_id=40,
            appointment_json={},
            requests={},
            appointments={},
        )
        db_session.add_all([doctor, workspace])
        await db_session.flush()

        svc = ContentAggregatorService(db_session)
        await svc.adjust_blog_comments(40, 2)
        await svc.adjust_reviews(40, 5, 1)
        await db_session.refresh(doctor)
        assert doctor.todays_glance == {} or "reviews" not in (doctor.todays_glance or {})

    async def test_webhook_pending_does_not_write_glance(
        self, db_session: AsyncSession
    ) -> None:
        doctor = DoctorDashboard(ph_user_id=884, todays_glance={})
        workspace = WorkspaceDoctorDashboard(
            workspace_id=1,
            ph_user_id=884,
            appointment_json={},
            requests={},
            appointments={},
        )
        db_session.add_all([doctor, workspace])
        await db_session.flush()

        svc = ContentAggregatorService(db_session)
        await svc.adjust_pending_reviews("884", 1)
        await svc.adjust_pending_reviews("884", 1)
        await svc.adjust_pending_reviews("884", -10)
        row = await db_session.get(ReviewsPendingAggregator, "884")
        assert row is not None
        assert row.pending_count == 0
        await db_session.refresh(doctor)
        assert doctor.todays_glance == {} or "reviews" not in (doctor.todays_glance or {})

    async def test_stored_glance_row_and_dashboard(self, db_session: AsyncSession) -> None:
        doctor = DoctorDashboard(ph_user_id=884, todays_glance={})
        workspace = WorkspaceDoctorDashboard(
            workspace_id=1,
            ph_user_id=884,
            appointment_json={},
            requests={},
            appointments={"kept": True},
        )
        db_session.add_all([doctor, workspace])
        await db_session.flush()

        svc = ContentAggregatorService(db_session)
        empty = await svc.get_glance("884")
        assert empty["content"]["reviews"]["pending_count"] == 0
        assert empty["content"]["blog_comments"]["pending_count"] == 0
        assert empty["content"]["podcast_comments"]["pending_count"] == 0
        assert empty["content"]["total_pending_counts"] == 0
        assert empty["appointments"] == {"kept": True}
        assert empty["payments"] == {}

        await svc.upsert_pending_glance(
            "884",
            {
                "reviews": {"pending_count": 2, "review_id": [3, 9]},
                "blog_comments": {
                    "pending_count": 1,
                    "comment_id": [2],
                    "blog_id": [5],
                },
                "podcast_comments": {
                    "pending_count": 0,
                    "comment_id": [],
                    "podcast_id": [],
                },
            },
        )

        glance = await svc.get_glance("884")
        assert glance["content"]["reviews"]["pending_count"] == 2
        assert glance["content"]["reviews"]["review_id"] == [3, 9]
        assert glance["content"]["blog_comments"]["pending_count"] == 1
        assert glance["content"]["blog_comments"]["comment_id"] == [2]
        assert glance["content"]["blog_comments"]["blog_id"] == [5]
        assert glance["content"]["podcast_comments"]["pending_count"] == 0
        assert glance["content"]["total_pending_counts"] == 3
        assert glance["appointments"] == {"kept": True}
        assert "messages" not in glance
        assert "linqmd_user_id" not in glance

        await db_session.refresh(doctor)
        await db_session.refresh(workspace)
        content = doctor.todays_glance
        assert content["reviews"]["pending_count"] == 2
        assert content["reviews"]["review_id"] == [3, 9]
        assert content["blog_comments"]["pending_count"] == 1
        assert content["total_pending_counts"] == 3
        assert "item_count" not in content["reviews"]
        assert workspace.appointments == {"kept": True}
        assert "content" not in workspace.appointments

    async def test_upsert_creates_dashboard_row_when_missing(
        self, db_session: AsyncSession
    ) -> None:
        svc = ContentAggregatorService(db_session)
        await svc.upsert_pending_glance(
            "884",
            {"reviews": 1, "blog_comments": 0, "podcast_comments": 0},
        )
        glance = await svc.get_glance("884")
        assert glance["content"]["reviews"]["pending_count"] == 1
        doctor = (
            await db_session.execute(
                select(DoctorDashboard).where(DoctorDashboard.ph_user_id == 884)
            )
        ).scalar_one()
        assert doctor.todays_glance["reviews"]["pending_count"] == 1
        workspace = (
            await db_session.execute(
                select(WorkspaceDoctorDashboard).where(
                    WorkspaceDoctorDashboard.ph_user_id == 884
                )
            )
        ).scalar_one()
        assert workspace.requests == {}
        assert workspace.appointments == {}

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

class TestReviewsAggregatorPending:
    async def test_seed_from_count_without_double_delta(
        self, db_session: AsyncSession
    ) -> None:
        db_session.add(
            Review(
                review_id="r1",
                user_id="884",
                status=ReviewStatus.PENDING.value,
                parent_review_id=None,
            )
        )
        await db_session.flush()

        svc = ContentAggregatorService(db_session)
        row = await svc.adjust_reviews_aggregator_pending("884", 1)
        assert row.pending_count == 1
        assert row.rating == 1
        assert row.rating_count == 0

        # Second event applies delta on existing row
        db_session.add(
            Review(
                review_id="r2",
                user_id="884",
                status=ReviewStatus.PENDING.value,
            )
        )
        await db_session.flush()
        row = await svc.adjust_reviews_aggregator_pending("884", 1)
        assert row.pending_count == 2

    async def test_floor_and_reply_ignored_via_delta(
        self, db_session: AsyncSession
    ) -> None:
        svc = ContentAggregatorService(db_session)
        row = await svc.adjust_reviews_aggregator_pending("885", 1)
        assert row.pending_count == 1
        row = await svc.adjust_reviews_aggregator_pending("885", -5)
        assert row.pending_count == 0

    async def test_adjust_does_not_write_glance_by_default(
        self, db_session: AsyncSession
    ) -> None:
        """Glance is filled by Practice Hub sync, not by aggregator deltas."""
        svc = ContentAggregatorService(db_session)
        await svc.adjust_reviews_aggregator_pending("884", 2)
        glance = await svc.get_glance("884")
        assert glance["content"]["reviews"]["pending_count"] == 0


class TestBlogPodcastCommentStats:
    async def test_blog_stats_per_blog_and_sum(
        self, db_session: AsyncSession
    ) -> None:
        svc = ContentAggregatorService(db_session)
        await svc.adjust_blog_comment_stats_pending(1, 50, 1, refresh_glance=False)
        await svc.adjust_blog_comment_stats_pending(1, 50, 1, refresh_glance=False)
        await svc.adjust_blog_comment_stats_pending(2, 50, 1, refresh_glance=False)
        row1 = (
            await db_session.execute(
                select(BlogCommentStats).where(
                    BlogCommentStats.blog_id == 1, BlogCommentStats.doctor_id == 50
                )
            )
        ).scalar_one()
        assert row1.pending_count == 2
        assert await svc.sum_blog_pending(50) == 3

        await svc.adjust_blog_comment_stats_pending(1, 50, -10, refresh_glance=False)
        assert row1.pending_count == 0

    async def test_podcast_stats(self, db_session: AsyncSession) -> None:
        svc = ContentAggregatorService(db_session)
        await svc.adjust_podcast_comment_stats_pending("p1", 60, 1, refresh_glance=False)
        await svc.adjust_podcast_comment_stats_pending("p1", 60, 1, refresh_glance=False)
        row = (
            await db_session.execute(
                select(PodcastCommentStats).where(
                    PodcastCommentStats.podcast_id == "p1",
                    PodcastCommentStats.doctor_id == 60,
                )
            )
        ).scalar_one()
        assert row.pending_count == 2
        await svc.adjust_podcast_comment_stats_pending("p1", 60, -1, refresh_glance=False)
        assert row.pending_count == 1

    async def test_sync_pending_glance_from_practice_hub(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import base64
        import json

        def _jwt(payload: dict) -> str:
            header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
            body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
            return f"{header}.{body}.sig"

        token = _jwt(
            {
                "appointment_doctor_id": "884",
                "user_id": "325",
                "workspace_id": "161",
            }
        )

        async def _fake_fetch(access_token: str) -> dict:
            return {
                "reviews": {"pending_count": 2, "review_id": [3]},
                "blog_comments": {
                    "pending_count": 1,
                    "comment_id": [2],
                    "blog_id": [5],
                },
                "podcast_comments": {
                    "pending_count": 0,
                    "comment_id": [],
                    "podcast_id": [],
                },
            }

        monkeypatch.setattr(
            "src.app.linq360.services.content_aggregator_service.fetch_pending_counts",
            _fake_fetch,
        )
        svc = ContentAggregatorService(db_session)
        glance = await svc.sync_pending_glance(token)
        assert glance["content"]["reviews"]["pending_count"] == 2
        assert glance["content"]["reviews"]["review_id"] == [3]
        assert glance["content"]["blog_comments"]["pending_count"] == 1
        assert glance["content"]["blog_comments"]["comment_id"] == [2]
        assert glance["content"]["blog_comments"]["blog_id"] == [5]
        assert glance["content"]["total_pending_counts"] == 3

        from sqlalchemy import select

        dash = (
            await db_session.execute(
                select(WorkspaceDoctorDashboard).where(
                    WorkspaceDoctorDashboard.ph_user_id == 884
                )
            )
        ).scalar_one()
        assert dash.workspace_id == 161
        assert dash.ws_user_id == 325
        doctor = (
            await db_session.execute(
                select(DoctorDashboard).where(DoctorDashboard.ph_user_id == 884)
            )
        ).scalar_one()
        assert doctor.ws_user_id == 325
        assert doctor.todays_glance["reviews"]["pending_count"] == 2


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
