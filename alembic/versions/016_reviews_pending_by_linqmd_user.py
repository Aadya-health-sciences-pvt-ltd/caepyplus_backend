"""Pending reviews keyed by Drupal linqmd_user_id.

Revision ID: 016
Revises: 015
Create Date: 2026-09-30

Doctor profiles for reviews often exist only in Drupal. Pending inbox rows
are keyed by ``linqmd_user_id`` (Drupal uid), not ``doctors.id``.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reviews_pending_aggregator",
        sa.Column("linqmd_user_id", sa.String(length=64), nullable=False),
        sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("doctor_id", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("linqmd_user_id"),
    )


def downgrade() -> None:
    op.drop_table("reviews_pending_aggregator")
