"""Reorder workspace_doctor_dashboard columns.

Revision ID: 023
Revises: 022
Create Date: 2026-10-28

Target order:
  appointment_id, ph_user_id, ws_user_id, workspace_id,
  appointments, requests, appointment_json
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "linq360"
_TABLE = "workspace_doctor_dashboard"
_FQ = f"{_SCHEMA}.{_TABLE}"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE {_FQ}__new (
            appointment_id SERIAL PRIMARY KEY,
            ph_user_id INTEGER NOT NULL,
            ws_user_id INTEGER,
            workspace_id INTEGER NOT NULL,
            appointments JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            requests JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            appointment_json JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
        """
    )
    op.execute(
        f"""
        INSERT INTO {_FQ}__new (
            appointment_id,
            ph_user_id,
            ws_user_id,
            workspace_id,
            appointments,
            requests,
            appointment_json
        )
        SELECT
            appointment_id,
            ph_user_id,
            ws_user_id,
            workspace_id,
            COALESCE(appointments, '{{}}'::jsonb),
            COALESCE(requests, '{{}}'::jsonb),
            COALESCE(appointment_json, '{{}}'::jsonb)
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
        f"CREATE INDEX ix_workspace_doctor_dashboard_ph_user_id "
        f"ON {_FQ} (ph_user_id)"
    )
    op.execute(
        f"CREATE INDEX ix_workspace_doctor_dashboard_ws_user_id "
        f"ON {_FQ} (ws_user_id)"
    )
    op.execute(
        f"CREATE INDEX ix_workspace_doctor_dashboard_workspace_id "
        f"ON {_FQ} (workspace_id)"
    )


def downgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE {_FQ}__old (
            appointment_id SERIAL PRIMARY KEY,
            appointment_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            workspace_id INTEGER NOT NULL,
            ws_user_id INTEGER,
            ph_user_id INTEGER NOT NULL,
            requests JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            appointments JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
        """
    )
    op.execute(
        f"""
        INSERT INTO {_FQ}__old (
            appointment_id,
            appointment_json,
            workspace_id,
            ws_user_id,
            ph_user_id,
            requests,
            appointments
        )
        SELECT
            appointment_id,
            COALESCE(appointment_json, '{{}}'::jsonb),
            workspace_id,
            ws_user_id,
            ph_user_id,
            COALESCE(requests, '{{}}'::jsonb),
            COALESCE(appointments, '{{}}'::jsonb)
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
        f"CREATE INDEX ix_workspace_doctor_dashboard_ws_user_id "
        f"ON {_FQ} (ws_user_id)"
    )
    op.execute(
        f"CREATE INDEX ix_workspace_doctor_dashboard_ph_user_id "
        f"ON {_FQ} (ph_user_id)"
    )
