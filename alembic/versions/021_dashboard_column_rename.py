"""Rename and reorder workspace_doctor_dashboard columns.

Revision ID: 021
Revises: 020
Create Date: 2026-10-23

Target layout:
  appointment_id, appointment_json, workspace_id, ws_user_id, ph_user_id, todays_glance

Renames:
  appointments_json → appointment_json
  workspace_user_id → ws_user_id
  user_id → ph_user_id
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "linq360"
_TABLE = "workspace_doctor_dashboard"
_FQ = f"{_SCHEMA}.{_TABLE}"


def upgrade() -> None:
    # Rebuild so physical column order matches the model.
    op.execute(
        f"""
        CREATE TABLE {_FQ}__new (
            appointment_id SERIAL PRIMARY KEY,
            appointment_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            workspace_id INTEGER NOT NULL,
            ws_user_id INTEGER,
            ph_user_id INTEGER NOT NULL,
            todays_glance JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
        """
    )
    op.execute(
        f"""
        INSERT INTO {_FQ}__new (
            appointment_id,
            appointment_json,
            workspace_id,
            ws_user_id,
            ph_user_id,
            todays_glance
        )
        SELECT
            appointment_id,
            COALESCE(appointments_json, '{{}}'::jsonb),
            workspace_id,
            workspace_user_id,
            user_id,
            COALESCE(todays_glance, '{{}}'::jsonb)
        FROM {_FQ}
        """
    )
    op.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence('{_FQ}__new', 'appointment_id'),
            COALESCE((SELECT MAX(appointment_id) FROM {_FQ}__new), 1),
            true
        )
        """
    )
    op.execute(f"DROP TABLE {_FQ}")
    op.execute(f"ALTER TABLE {_FQ}__new RENAME TO {_TABLE}")
    op.execute(
        f"CREATE INDEX ix_workspace_doctor_dashboard_workspace_id "
        f"ON {_FQ} (workspace_id)"
    )
    op.execute(
        f"CREATE INDEX ix_workspace_doctor_dashboard_ws_user_id "
        f"ON {_FQ} (ws_user_id)"
    )
    op.execute(
        f"CREATE INDEX ix_workspace_doctor_dashboard_ph_user_id "
        f"ON {_FQ} (ph_user_id)"
    )


def downgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE {_FQ}__old (
            appointment_id SERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            appointments_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            todays_glance JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            workspace_user_id INTEGER
        )
        """
    )
    op.execute(
        f"""
        INSERT INTO {_FQ}__old (
            appointment_id,
            workspace_id,
            user_id,
            appointments_json,
            todays_glance,
            workspace_user_id
        )
        SELECT
            appointment_id,
            workspace_id,
            ph_user_id,
            COALESCE(appointment_json, '{{}}'::jsonb),
            COALESCE(todays_glance, '{{}}'::jsonb),
            ws_user_id
        FROM {_FQ}
        """
    )
    op.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence('{_FQ}__old', 'appointment_id'),
            COALESCE((SELECT MAX(appointment_id) FROM {_FQ}__old), 1),
            true
        )
        """
    )
    op.execute(f"DROP TABLE {_FQ}")
    op.execute(f"ALTER TABLE {_FQ}__old RENAME TO {_TABLE}")
    op.execute(
        f"CREATE INDEX ix_workspace_doctor_dashboard_workspace_id "
        f"ON {_FQ} (workspace_id)"
    )
    op.execute(
        f"CREATE INDEX ix_workspace_doctor_dashboard_user_id "
        f"ON {_FQ} (user_id)"
    )
    op.execute(
        f"CREATE INDEX ix_workspace_doctor_dashboard_workspace_user_id "
        f"ON {_FQ} (workspace_user_id)"
    )
