"""Add lead_doctors table.

Revision ID: 002
Revises: 001
Create Date: 2026-03-09

Creates the ``lead_doctors`` table for storing lead doctor data imported from
external platforms (e.g. Practo CSV exports).

Indexes
-------
Single-column B-tree indexes on:
  - city, speciality, doctor_name, specialization, location, hospital_name
  (the most common API filter columns)

Composite B-tree indexes for multi-column filter patterns:
  - (city, speciality)       — "all dentists in Mumbai"
  - (city, hospital_name)    — "all doctors at Apollo in Bangalore"
  - (speciality, location)   — "all cardiologists in a specific area"

Rollback
--------
``downgrade()`` drops all indexes and then the table.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =======================================================================
    # 1. CREATE TABLE
    # =======================================================================
    op.create_table(
        "lead_doctors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Core profile
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("speciality", sa.Text(), nullable=True),
        sa.Column("doctor_name", sa.Text(), nullable=True),
        sa.Column("qualification", sa.Text(), nullable=True),
        sa.Column("specialization", sa.Text(), nullable=True),
        sa.Column("experience", sa.Text(), nullable=True),
        sa.Column("fee", sa.Text(), nullable=True),
        # Location / Hospital
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("hospital_name", sa.Text(), nullable=True),
        sa.Column("hospital_address", sa.Text(), nullable=True),
        # Credentials & Recognition
        sa.Column("awards", sa.Text(), nullable=True),
        sa.Column("memberships", sa.Text(), nullable=True),
        sa.Column("registrations", sa.Text(), nullable=True),
        # Services & Profile
        sa.Column("services", sa.Text(), nullable=True),
        sa.Column("profile_url", sa.Text(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # =======================================================================
    # 2. SINGLE-COLUMN INDEXES — high-cardinality filter columns
    # =======================================================================
    op.create_index("ix_lead_doctors_city", "lead_doctors", ["city"])
    op.create_index("ix_lead_doctors_speciality", "lead_doctors", ["speciality"])
    op.create_index("ix_lead_doctors_doctor_name", "lead_doctors", ["doctor_name"])
    op.create_index("ix_lead_doctors_specialization", "lead_doctors", ["specialization"])
    op.create_index("ix_lead_doctors_location", "lead_doctors", ["location"])
    op.create_index("ix_lead_doctors_hospital_name", "lead_doctors", ["hospital_name"])

    # =======================================================================
    # 3. COMPOSITE INDEXES — common multi-column filter patterns
    # =======================================================================
    # "Find all dentists in Mumbai"
    op.create_index(
        "ix_lead_doctors_city_speciality",
        "lead_doctors",
        ["city", "speciality"],
    )
    # "Find all doctors at Apollo in Bangalore"
    op.create_index(
        "ix_lead_doctors_city_hospital",
        "lead_doctors",
        ["city", "hospital_name"],
    )
    # "Find all cardiologists in a specific area"
    op.create_index(
        "ix_lead_doctors_speciality_location",
        "lead_doctors",
        ["speciality", "location"],
    )


def downgrade() -> None:
    """Drop indexes and table in reverse order."""
    # Composite indexes
    op.drop_index("ix_lead_doctors_speciality_location", table_name="lead_doctors")
    op.drop_index("ix_lead_doctors_city_hospital", table_name="lead_doctors")
    op.drop_index("ix_lead_doctors_city_speciality", table_name="lead_doctors")
    # Single-column indexes
    op.drop_index("ix_lead_doctors_hospital_name", table_name="lead_doctors")
    op.drop_index("ix_lead_doctors_location", table_name="lead_doctors")
    op.drop_index("ix_lead_doctors_specialization", table_name="lead_doctors")
    op.drop_index("ix_lead_doctors_doctor_name", table_name="lead_doctors")
    op.drop_index("ix_lead_doctors_speciality", table_name="lead_doctors")
    op.drop_index("ix_lead_doctors_city", table_name="lead_doctors")
    # Table
    op.drop_table("lead_doctors")
