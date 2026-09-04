"""Create PostgreSQL schema linq360 and dashboard table shells.

Revision ID: 008
Revises: 007
Create Date: 2026-09-03

Creates schema ``linq360`` with empty table shells:
- workspace_doctor_dashboard (id PK only)
- doctor_dashboard (id PK only)

Business columns will be added in later migrations.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS linq360")
    op.create_table(
        "workspace_doctor_dashboard",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="linq360",
    )
    op.create_table(
        "doctor_dashboard",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="linq360",
    )


def downgrade() -> None:
    op.drop_table("doctor_dashboard", schema="linq360")
    op.drop_table("workspace_doctor_dashboard", schema="linq360")
    op.execute("DROP SCHEMA IF EXISTS linq360")
