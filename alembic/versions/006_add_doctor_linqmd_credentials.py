"""Add doctor_linqmd_credentials table.

Revision ID: 006
Revises: 005
Create Date: 2026-05-23

Stores LinQMD user id, username, and initial password after successful
admin profile creation sync.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "doctor_linqmd_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("doctor_id", sa.BigInteger(), nullable=False),
        sa.Column("doctor_name", sa.Text(), nullable=False),
        sa.Column("linqmd_user_id", sa.String(length=64), nullable=False),
        sa.Column("linqmd_username", sa.String(length=255), nullable=False),
        sa.Column("linqmd_password", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doctor_id", name="uq_doctor_linqmd_credentials_doctor_id"),
    )
    op.create_index(
        "ix_doctor_linqmd_credentials_doctor_id",
        "doctor_linqmd_credentials",
        ["doctor_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_doctor_linqmd_credentials_doctor_id", table_name="doctor_linqmd_credentials")
    op.drop_table("doctor_linqmd_credentials")
