"""Unique workspace_doctor_dashboard on (ws_user_id, ph_user_id, workspace_id).

Revision ID: 025
Revises: 024
Create Date: 2026-10-29

- Drop unique index ``(ph_user_id, workspace_id)`` (created by 024 as an index)
- Add unique index ``(ws_user_id, ph_user_id, workspace_id)``
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "linq360"
_TABLE = "workspace_doctor_dashboard"


def upgrade() -> None:
    op.drop_index(
        "uq_workspace_doctor_dashboard_ph_workspace",
        table_name=_TABLE,
        schema=_SCHEMA,
    )
    op.create_index(
        "uq_workspace_doctor_dashboard_ws_ph_workspace",
        _TABLE,
        ["ws_user_id", "ph_user_id", "workspace_id"],
        unique=True,
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_workspace_doctor_dashboard_ws_ph_workspace",
        table_name=_TABLE,
        schema=_SCHEMA,
    )
    op.create_index(
        "uq_workspace_doctor_dashboard_ph_workspace",
        _TABLE,
        ["ph_user_id", "workspace_id"],
        unique=True,
        schema=_SCHEMA,
    )
