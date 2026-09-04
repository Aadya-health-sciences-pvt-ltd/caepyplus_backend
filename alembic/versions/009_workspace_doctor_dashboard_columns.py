"""Add workspace_doctor_dashboard business columns.

Revision ID: 009
Revises: 008
Create Date: 2026-09-03

Renames PK ``id`` → ``appointment_id`` and adds appointment/patient fields
on ``linq360.workspace_doctor_dashboard``. Leaves ``doctor_dashboard`` unchanged.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
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
    op.alter_column(
        "workspace_doctor_dashboard",
        "id",
        new_column_name="appointment_id",
        existing_type=sa.Integer(),
        schema="linq360",
    )
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


def downgrade() -> None:
    op.drop_column("workspace_doctor_dashboard", "time_slot", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "consultation_type", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "last_name", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "first_name", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "patient_name", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "appointment_type", schema="linq360")
    op.drop_column("workspace_doctor_dashboard", "patient_meta_code", schema="linq360")
    op.alter_column(
        "workspace_doctor_dashboard",
        "appointment_id",
        new_column_name="id",
        existing_type=sa.Integer(),
        schema="linq360",
    )
