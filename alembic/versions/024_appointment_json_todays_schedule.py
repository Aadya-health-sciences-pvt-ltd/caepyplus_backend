"""Normalize appointment_json to todays_schedule; unique (ph_user_id, workspace_id).

Revision ID: 024
Revises: 023
Create Date: 2026-10-29

- Migrate ``appointment_json`` to ``{ "todays_schedule": [ ... ] }``
- Deduplicate rows sharing (ph_user_id, workspace_id)
- Add unique index on (ph_user_id, workspace_id)
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "linq360"
_TABLE = "workspace_doctor_dashboard"
_FQ = f"{_SCHEMA}.{_TABLE}"


def upgrade() -> None:
    # Wrap flat patient objects / empty JSON into todays_schedule array.
    op.execute(
        f"""
        UPDATE {_FQ}
        SET appointment_json = CASE
            WHEN appointment_json IS NULL
              OR appointment_json = 'null'::jsonb
              OR appointment_json = '{{}}'::jsonb
            THEN '{{"todays_schedule": []}}'::jsonb
            WHEN jsonb_typeof(appointment_json -> 'todays_schedule') = 'array'
            THEN appointment_json
            WHEN jsonb_typeof(appointment_json) = 'array'
            THEN jsonb_build_object('todays_schedule', appointment_json)
            WHEN jsonb_typeof(appointment_json) = 'object'
             AND appointment_json ? 'patient_meta_code'
            THEN jsonb_build_object(
                'todays_schedule',
                jsonb_build_array(appointment_json)
            )
            ELSE jsonb_build_object('todays_schedule', '[]'::jsonb)
        END
        """
    )

    # Merge duplicate (ph_user_id, workspace_id): keep lowest appointment_id,
    # concatenate todays_schedule arrays from duplicates into the keeper.
    op.execute(
        f"""
        WITH ranked AS (
            SELECT
                appointment_id,
                ph_user_id,
                workspace_id,
                appointment_json,
                ROW_NUMBER() OVER (
                    PARTITION BY ph_user_id, workspace_id
                    ORDER BY appointment_id
                ) AS rn
            FROM {_FQ}
        ),
        merged AS (
            SELECT
                MIN(appointment_id) AS keep_id,
                ph_user_id,
                workspace_id,
                jsonb_build_object(
                    'todays_schedule',
                    COALESCE(
                        (
                            SELECT jsonb_agg(elem)
                            FROM ranked r2,
                                 LATERAL jsonb_array_elements(
                                     COALESCE(
                                         r2.appointment_json -> 'todays_schedule',
                                         '[]'::jsonb
                                     )
                                 ) AS elem
                            WHERE r2.ph_user_id = ranked.ph_user_id
                              AND r2.workspace_id = ranked.workspace_id
                        ),
                        '[]'::jsonb
                    )
                ) AS schedule
            FROM ranked
            GROUP BY ph_user_id, workspace_id
            HAVING COUNT(*) > 1
        )
        UPDATE {_FQ} w
        SET appointment_json = m.schedule
        FROM merged m
        WHERE w.appointment_id = m.keep_id
        """
    )
    op.execute(
        f"""
        DELETE FROM {_FQ} w
        USING (
            SELECT appointment_id
            FROM (
                SELECT
                    appointment_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY ph_user_id, workspace_id
                        ORDER BY appointment_id
                    ) AS rn
                FROM {_FQ}
            ) d
            WHERE d.rn > 1
        ) dup
        WHERE w.appointment_id = dup.appointment_id
        """
    )

    op.create_index(
        "uq_workspace_doctor_dashboard_ph_workspace",
        _TABLE,
        ["ph_user_id", "workspace_id"],
        unique=True,
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_workspace_doctor_dashboard_ph_workspace",
        table_name=_TABLE,
        schema=_SCHEMA,
    )
    # Unwrap first schedule item back to a flat object when length is 1;
    # leave arrays of 0/2+ as the wrapped object (best-effort).
    op.execute(
        f"""
        UPDATE {_FQ}
        SET appointment_json = CASE
            WHEN jsonb_typeof(appointment_json -> 'todays_schedule') = 'array'
             AND jsonb_array_length(appointment_json -> 'todays_schedule') = 1
            THEN appointment_json -> 'todays_schedule' -> 0
            WHEN jsonb_typeof(appointment_json -> 'todays_schedule') = 'array'
             AND jsonb_array_length(appointment_json -> 'todays_schedule') = 0
            THEN '{{}}'::jsonb
            ELSE appointment_json
        END
        """
    )
