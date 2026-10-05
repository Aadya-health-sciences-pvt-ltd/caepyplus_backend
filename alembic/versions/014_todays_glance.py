"""Add todays_glance JSONB to workspace_doctor_dashboard.

Revision ID: 014
Revises: 013
Create Date: 2026-09-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()
    server_default = (
        sa.text("'{}'::jsonb") if bind.dialect.name == "postgresql" else sa.text("'{}'")
    )
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column(
            "todays_glance",
            json_type,
            nullable=False,
            server_default=server_default,
        ),
        schema="linq360",
    )


def downgrade() -> None:
    op.drop_column("workspace_doctor_dashboard", "todays_glance", schema="linq360")
