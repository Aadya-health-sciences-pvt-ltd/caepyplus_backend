"""Widen verbal_intro_file to TEXT for AI-generated LinQMD overview.

Revision ID: 007
Revises: 006
Create Date: 2026-06-06

Repurposes verbal_intro_file to store patient-facing profile overview text
(80-200 words) generated at LinQMD profile create time.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "doctors",
        "verbal_intro_file",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=True,
        comment="AI-generated patient-facing profile overview (LinQMD create only)",
    )


def downgrade() -> None:
    op.alter_column(
        "doctors",
        "verbal_intro_file",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=True,
        comment="Verbal introduction file URL",
    )
