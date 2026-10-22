"""Pending counter tables and comment/review mirrors.

Revision ID: 019
Revises: 018
Create Date: 2026-10-22

- public.reviews_aggregator
- public.blog_comment_stats
- public.podcast_comment_stats
- public.reviews (status mirror)
- public.podcast_comments (status mirror)
- blog_comments.parent_comment_id
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reviews_aggregator",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("doctor_id", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "blog_comment_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("blog_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blog_id", "doctor_id", name="uq_blog_comment_stats_blog_doctor"),
    )
    op.create_index("ix_blog_comment_stats_blog_id", "blog_comment_stats", ["blog_id"])
    op.create_index("ix_blog_comment_stats_doctor_id", "blog_comment_stats", ["doctor_id"])

    op.create_table(
        "podcast_comment_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("podcast_id", sa.String(length=100), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "podcast_id", "doctor_id", name="uq_podcast_comment_stats_podcast_doctor"
        ),
    )
    op.create_index("ix_podcast_comment_stats_podcast_id", "podcast_comment_stats", ["podcast_id"])
    op.create_index("ix_podcast_comment_stats_doctor_id", "podcast_comment_stats", ["doctor_id"])

    op.create_table(
        "reviews",
        sa.Column("review_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("parent_review_id", sa.String(length=100), nullable=True),
        sa.Column("doctor_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("review_id"),
    )
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"])
    op.create_index("ix_reviews_status", "reviews", ["status"])
    op.create_index("ix_reviews_parent_review_id", "reviews", ["parent_review_id"])

    op.create_table(
        "podcast_comments",
        sa.Column("comment_id", sa.String(length=100), nullable=False),
        sa.Column("podcast_id", sa.String(length=100), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("parent_comment_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("comment_id"),
    )
    op.create_index("ix_podcast_comments_podcast_id", "podcast_comments", ["podcast_id"])
    op.create_index("ix_podcast_comments_doctor_id", "podcast_comments", ["doctor_id"])
    op.create_index("ix_podcast_comments_status", "podcast_comments", ["status"])
    op.create_index(
        "ix_podcast_comments_parent_comment_id", "podcast_comments", ["parent_comment_id"]
    )

    op.add_column(
        "blog_comments",
        sa.Column("parent_comment_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_blog_comments_parent_comment_id", "blog_comments", ["parent_comment_id"]
    )
    op.create_foreign_key(
        "fk_blog_comments_parent_comment_id",
        "blog_comments",
        "blog_comments",
        ["parent_comment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_blog_comments_parent_comment_id", "blog_comments", type_="foreignkey")
    op.drop_index("ix_blog_comments_parent_comment_id", table_name="blog_comments")
    op.drop_column("blog_comments", "parent_comment_id")

    op.drop_index("ix_podcast_comments_parent_comment_id", table_name="podcast_comments")
    op.drop_index("ix_podcast_comments_status", table_name="podcast_comments")
    op.drop_index("ix_podcast_comments_doctor_id", table_name="podcast_comments")
    op.drop_index("ix_podcast_comments_podcast_id", table_name="podcast_comments")
    op.drop_table("podcast_comments")

    op.drop_index("ix_reviews_parent_review_id", table_name="reviews")
    op.drop_index("ix_reviews_status", table_name="reviews")
    op.drop_index("ix_reviews_user_id", table_name="reviews")
    op.drop_table("reviews")

    op.drop_index("ix_podcast_comment_stats_doctor_id", table_name="podcast_comment_stats")
    op.drop_index("ix_podcast_comment_stats_podcast_id", table_name="podcast_comment_stats")
    op.drop_table("podcast_comment_stats")

    op.drop_index("ix_blog_comment_stats_doctor_id", table_name="blog_comment_stats")
    op.drop_index("ix_blog_comment_stats_blog_id", table_name="blog_comment_stats")
    op.drop_table("blog_comment_stats")

    op.drop_table("reviews_aggregator")
