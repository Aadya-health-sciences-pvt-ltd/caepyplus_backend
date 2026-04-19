"""Store practice_segments as JSON array of strings.

Revision ID: 005
Revises: 004
Create Date: 2026-04-15

Previously ``practice_segments`` was a single VARCHAR(50), which could not
represent multiple selections from onboarding. Values are migrated by
splitting legacy comma-separated text into a JSON array.

PostgreSQL does not allow scalar subqueries inside ``ALTER COLUMN ... USING``,
so the upgrade uses only scalar expressions (``regexp_split_to_array`` +
``to_jsonb``). Downgrade uses a temporary column and ``UPDATE`` because
``USING`` cannot aggregate JSON array elements in one expression.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                ALTER TABLE doctors
                ALTER COLUMN practice_segments TYPE jsonb
                USING (
                    CASE
                        WHEN practice_segments IS NULL OR btrim(practice_segments::text) = ''
                        THEN '[]'::jsonb
                        ELSE to_jsonb(
                            array_remove(
                                regexp_split_to_array(
                                    btrim(practice_segments::text),
                                    '\\s*,\\s*'
                                ),
                                ''
                            )
                        )
                    END
                );
                """
            )
        )
        op.execute(sa.text("ALTER TABLE doctors ALTER COLUMN practice_segments SET DEFAULT '[]'::jsonb;"))
        op.execute(sa.text("ALTER TABLE doctors ALTER COLUMN practice_segments SET NOT NULL;"))
    else:
        op.alter_column(
            "doctors",
            "practice_segments",
            existing_type=sa.String(50),
            type_=sa.JSON(),
            nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.add_column(
            "doctors",
            sa.Column("practice_segments_legacy", sa.String(50), nullable=True),
        )
        op.execute(
            sa.text(
                """
                UPDATE doctors AS d
                SET practice_segments_legacy = LEFT(
                    (
                        SELECT string_agg(value, ', ')
                        FROM jsonb_array_elements_text(d.practice_segments)
                    ),
                    50
                )
                WHERE d.practice_segments IS NOT NULL
                  AND d.practice_segments <> '[]'::jsonb;
                """
            )
        )
        op.drop_column("doctors", "practice_segments")
        op.execute(sa.text("ALTER TABLE doctors RENAME COLUMN practice_segments_legacy TO practice_segments;"))
    else:
        op.alter_column(
            "doctors",
            "practice_segments",
            existing_type=sa.JSON(),
            type_=sa.String(50),
            nullable=True,
        )
