"""Add appointments_json column to workspace_doctor_dashboard.

Revision ID: 010
Revises: 009
Create Date: 2026-09-03

Stores one or more appointment objects as a JSON array on
``linq360.workspace_doctor_dashboard``. No API in this revision.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()
    server_default = (
        sa.text("'[]'::jsonb") if bind.dialect.name == "postgresql" else sa.text("'[]'")
    )
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column(
            "appointments_json",
            json_type,
            nullable=False,
            server_default=server_default,
        ),
        schema="linq360",
    )


def downgrade() -> None:
    op.drop_column("workspace_doctor_dashboard", "appointments_json", schema="linq360")
