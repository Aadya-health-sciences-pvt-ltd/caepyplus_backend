"""Add pending_count to reviews_summary_aggregator.

Revision ID: 015
Revises: 014
Create Date: 2026-09-29

Tracks all still-pending reviews for todays_glance (Approve & Publish inbox).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reviews_summary_aggregator",
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("reviews_summary_aggregator", "pending_count")
