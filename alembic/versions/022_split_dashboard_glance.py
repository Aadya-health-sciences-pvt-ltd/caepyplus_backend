"""Split glance: content on doctor_dashboard; requests/appointments on workspace.

Revision ID: 022
Revises: 021
Create Date: 2026-10-28

- Expand ``doctor_dashboard``: ph_user_id, ws_user_id, todays_glance (content only)
- Add ``requests`` / ``appointments`` JSONB on ``workspace_doctor_dashboard``
- Migrate data from ``workspace_doctor_dashboard.todays_glance``
- Drop ``todays_glance`` from ``workspace_doctor_dashboard``
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = "linq360"
_WS = "workspace_doctor_dashboard"
_DD = "doctor_dashboard"
_WS_FQ = f"{_SCHEMA}.{_WS}"
_DD_FQ = f"{_SCHEMA}.{_DD}"


def upgrade() -> None:
    op.add_column(
        _DD,
        sa.Column("ph_user_id", sa.Integer(), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        _DD,
        sa.Column("ws_user_id", sa.Integer(), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        _DD,
        sa.Column(
            "todays_glance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_doctor_dashboard_ph_user_id",
        _DD,
        ["ph_user_id"],
        unique=True,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_doctor_dashboard_ws_user_id",
        _DD,
        ["ws_user_id"],
        schema=_SCHEMA,
    )

    op.add_column(
        _WS,
        sa.Column(
            "requests",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=_SCHEMA,
    )
    op.add_column(
        _WS,
        sa.Column(
            "appointments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=_SCHEMA,
    )

    # One doctor_dashboard row per ph_user_id; content from first workspace glance.
    op.execute(
        f"""
        INSERT INTO {_DD_FQ} (ph_user_id, ws_user_id, todays_glance)
        SELECT sub.ph_user_id, sub.ws_user_id, sub.content
        FROM (
            SELECT DISTINCT ON (ph_user_id)
                ph_user_id,
                ws_user_id,
                CASE
                    WHEN jsonb_typeof(todays_glance -> 'content') = 'object'
                    THEN todays_glance -> 'content'
                    WHEN todays_glance ? 'reviews'
                      OR todays_glance ? 'blog_comments'
                      OR todays_glance ? 'podcast_comments'
                    THEN todays_glance
                    ELSE '{{}}'::jsonb
                END AS content
            FROM {_WS_FQ}
            WHERE ph_user_id IS NOT NULL
            ORDER BY ph_user_id, appointment_id
        ) AS sub
        WHERE NOT EXISTS (
            SELECT 1 FROM {_DD_FQ} d WHERE d.ph_user_id = sub.ph_user_id
        )
        """
    )

    op.execute(
        f"""
        UPDATE {_WS_FQ}
        SET
            requests = CASE
                WHEN jsonb_typeof(todays_glance -> 'requests') = 'object'
                THEN todays_glance -> 'requests'
                ELSE '{{}}'::jsonb
            END,
            appointments = CASE
                WHEN jsonb_typeof(todays_glance -> 'appointments') = 'object'
                THEN todays_glance -> 'appointments'
                ELSE '{{}}'::jsonb
            END
        """
    )

    op.drop_column(_WS, "todays_glance", schema=_SCHEMA)

    # ph_user_id required going forward for new rows; existing empty doctor_dashboard
    # scaffold rows (id only) may have null — leave nullable for empty shells,
    # app always sets ph_user_id on upsert.
    op.execute(f"DELETE FROM {_DD_FQ} WHERE ph_user_id IS NULL AND todays_glance = '{{}}'::jsonb")


def downgrade() -> None:
    op.add_column(
        _WS,
        sa.Column(
            "todays_glance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=_SCHEMA,
    )

    op.execute(
        f"""
        UPDATE {_WS_FQ} w
        SET todays_glance = jsonb_build_object(
            'content', COALESCE(d.todays_glance, '{{}}'::jsonb),
            'requests', COALESCE(w.requests, '{{}}'::jsonb),
            'appointments', COALESCE(w.appointments, '{{}}'::jsonb),
            'payments', '{{}}'::jsonb
        )
        FROM {_DD_FQ} d
        WHERE d.ph_user_id = w.ph_user_id
        """
    )
    op.execute(
        f"""
        UPDATE {_WS_FQ}
        SET todays_glance = jsonb_build_object(
            'content', '{{}}'::jsonb,
            'requests', COALESCE(requests, '{{}}'::jsonb),
            'appointments', COALESCE(appointments, '{{}}'::jsonb),
            'payments', '{{}}'::jsonb
        )
        WHERE todays_glance = '{{}}'::jsonb
           OR todays_glance IS NULL
        """
    )

    op.drop_column(_WS, "appointments", schema=_SCHEMA)
    op.drop_column(_WS, "requests", schema=_SCHEMA)

    op.drop_index("ix_doctor_dashboard_ws_user_id", table_name=_DD, schema=_SCHEMA)
    op.drop_index("ix_doctor_dashboard_ph_user_id", table_name=_DD, schema=_SCHEMA)
    op.drop_column(_DD, "todays_glance", schema=_SCHEMA)
    op.drop_column(_DD, "ws_user_id", schema=_SCHEMA)
    op.drop_column(_DD, "ph_user_id", schema=_SCHEMA)
