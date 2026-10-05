"""Store LinQ360 pending counts synced from Practice Hub.

Revision ID: 017
Revises: 016
Create Date: 2026-09-30

One row per Drupal uid. Glance GET reads this table only.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_table("content_pending_glance")
