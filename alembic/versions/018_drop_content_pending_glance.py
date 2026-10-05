"""Drop public content_pending_glance.

Revision ID: 018
Revises: 017
Create Date: 2026-09-30

Pending counts live in linq360.workspace_doctor_dashboard.todays_glance.
Copy any stored counts onto matching dashboard rows, then drop the public table.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE linq360.workspace_doctor_dashboard AS d
                SET todays_glance = jsonb_set(
                    COALESCE(d.todays_glance, '{}'::jsonb),
                    '{content}',
                    jsonb_build_object(
                        'reviews', jsonb_build_object('pending_count', g.reviews_pending_count),
                        'blog_comments', jsonb_build_object(
                            'pending_count', g.blog_comments_pending_count
                        ),
                        'podcast_comments', jsonb_build_object(
                            'pending_count', g.podcast_comments_pending_count
                        )
                    ),
                    true
                )
                FROM content_pending_glance AS g
                WHERE d.user_id::text = g.linqmd_user_id
                """
            )
        )
    op.drop_table("content_pending_glance")


def downgrade() -> None:
    op.create_table(
        "content_pending_glance",
        sa.Column("linqmd_user_id", sa.String(length=64), nullable=False),
        sa.Column("reviews_pending_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "blog_comments_pending_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "podcast_comments_pending_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("linqmd_user_id"),
    )
