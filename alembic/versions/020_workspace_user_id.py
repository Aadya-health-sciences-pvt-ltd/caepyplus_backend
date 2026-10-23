"""Add workspace_user_id to workspace_doctor_dashboard.

Revision ID: 020
Revises: 019
Create Date: 2026-10-23

Stores the portal workspace user id from the workspace select token
(``user_id`` claim) after ``workspace_id``. ``user_id`` remains the Drupal
doctor uid (``appointment_doctor_id``).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column("workspace_user_id", sa.Integer(), nullable=True),
        schema="linq360",
    )
    op.create_index(
        "ix_workspace_doctor_dashboard_workspace_user_id",
        "workspace_doctor_dashboard",
        ["workspace_user_id"],
        schema="linq360",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_doctor_dashboard_workspace_user_id",
        table_name="workspace_doctor_dashboard",
        schema="linq360",
    )
    op.drop_column("workspace_doctor_dashboard", "workspace_user_id", schema="linq360")
