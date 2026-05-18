"""Allow NULL users.phone for Google / email-first sign-up.

Revision ID: 004
Revises: 003
Create Date: 2026-04-15

The ORM already treats ``User.phone`` as optional; the initial schema had
``NOT NULL`` on PostgreSQL, which breaks creating RBAC rows when no phone
exists yet (e.g. Google Sign-In before onboarding collects a number).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "phone",
        existing_type=sa.String(20),
        nullable=True,
        existing_comment="Phone number with country code",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "phone",
        existing_type=sa.String(20),
        nullable=False,
        existing_comment="Phone number with country code",
    )
