"""Store appointments_json as a single JSON object (not an array).

Revision ID: 012
Revises: 011
Create Date: 2026-09-04
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            """
            UPDATE linq360.workspace_doctor_dashboard
            SET appointments_json = CASE
                WHEN jsonb_typeof(appointments_json) = 'array'
                THEN COALESCE(appointments_json -> 0, '{}'::jsonb)
                ELSE appointments_json
            END
            """
        )
    )
    op.alter_column(
        "workspace_doctor_dashboard",
        "appointments_json",
        server_default=sa.text("'{}'::jsonb"),
        schema="linq360",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            """
            UPDATE linq360.workspace_doctor_dashboard
            SET appointments_json = CASE
                WHEN jsonb_typeof(appointments_json) = 'object'
                THEN jsonb_build_array(appointments_json)
                ELSE appointments_json
            END
            """
        )
    )
    op.alter_column(
        "workspace_doctor_dashboard",
        "appointments_json",
        server_default=sa.text("'[]'::jsonb"),
        schema="linq360",
    )
