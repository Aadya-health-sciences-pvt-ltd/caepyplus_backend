"""Create content aggregator tables (public + linq360).

Revision ID: 013
Revises: 012
Create Date: 2026-09-29

- public.blog_comments_aggregator
- public.podcast_comments_aggregator
- public.reviews_summary_aggregator
- linq360.content_source_aggregator
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()
    empty_json = (
        sa.text("'{}'::jsonb") if bind.dialect.name == "postgresql" else sa.text("'{}'")
    )

    op.create_table(
        "blog_comments_aggregator",
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("doctor_id"),
    )

    op.create_table(
        "podcast_comments_aggregator",
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("doctor_id"),
    )

    op.create_table(
        "reviews_summary_aggregator",
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_sum", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("avg_rating", sa.Numeric(8, 4), nullable=True),
        sa.Column("linqmd_user_id", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("doctor_id"),
    )

    op.create_table(
        "content_source_aggregator",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_rating", sa.Numeric(8, 4), nullable=True),
        sa.Column("rating_sum", sa.Numeric(12, 2), nullable=True),
        sa.Column("metrics", json_type, nullable=False, server_default=empty_json),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doctor_id", "source", name="uq_content_source_aggregator_doctor_source"),
        schema="linq360",
    )
    op.create_index(
        "ix_content_source_aggregator_doctor_id",
        "content_source_aggregator",
        ["doctor_id"],
        unique=False,
        schema="linq360",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_content_source_aggregator_doctor_id",
        table_name="content_source_aggregator",
        schema="linq360",
    )
    op.drop_table("content_source_aggregator", schema="linq360")
    op.drop_table("reviews_summary_aggregator")
    op.drop_table("podcast_comments_aggregator")
    op.drop_table("blog_comments_aggregator")
