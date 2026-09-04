"""Trim workspace_doctor_dashboard to four columns.

Revision ID: 011
Revises: 010
Create Date: 2026-09-04

Keeps ``appointment_id`` and ``appointments_json``. Adds ``workspace_id``
and ``user_id``. Drops flat patient/slot columns (those details live in JSON).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_appointment_type = sa.Enum(
    "REQUEST",
    "BOOKING",
    "CALL",
    name="linq360_appointment_type",
    native_enum=False,
)
_consultation_type = sa.Enum(
    "in-person",
    "teleconsultation",
    name="linq360_consultation_type",
    native_enum=False,
)


def upgrade() -> None:
    op.drop_column("workspace_doctor_dashboard", "time_slot", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "consultation_type", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "last_name", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "first_name", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "patient_name", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "appointment_type", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "patient_meta_code", schema="linq360")
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        schema="linq360",
    )
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column("user_id", sa.Integer(), nullable=False),
        schema="linq360",
    )
    op.create_index(
        "ix_workspace_doctor_dashboard_workspace_id",
        "workspace_doctor_dashboard",
        ["workspace_id"],
        schema="linq360",
    )
    op.create_index(
        "ix_workspace_doctor_dashboard_user_id",
        "workspace_doctor_dashboard",
        ["user_id"],
        schema="linq360",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_doctor_dashboard_user_id",
        table_name="workspace_doctor_dashboard",
        schema="linq360",
    )
    op.drop_index(
        "ix_workspace_doctor_dashboard_workspace_id",
        table_name="workspace_doctor_dashboard",
        schema="linq360",
    )
    op.drop_column("workspace_doctor_dashboard", "user_id", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "workspace_id", schema="linq360")
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column("patient_meta_code", sa.String(length=255), nullable=False),
        schema="linq360",
    )
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column("appointment_type", _appointment_type, nullable=False),
        schema="linq360",
    )
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column("patient_name", sa.String(length=255), nullable=False),
        schema="linq360",
    )
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column("first_name", sa.String(length=255), nullable=False),
        schema="linq360",
    )
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column("last_name", sa.String(length=255), nullable=False),
        schema="linq360",
    )
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column("consultation_type", _consultation_type, nullable=False),
        schema="linq360",
    )
    op.add_column(
        "workspace_doctor_dashboard",
        sa.Column("time_slot", sa.String(length=255), nullable=False),
        schema="linq360",
    )
