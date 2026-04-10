"""
Lead Doctor Model.

SQLAlchemy 2.0 ORM model for the ``lead_doctors`` table.

This table holds lead doctor data imported from external sources (e.g. Practo).
All columns are TEXT to accommodate the loosely-structured CSV data.
The table is designed for read-heavy, filter-based querying by city,
speciality, location, hospital, and doctor name.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.session import Base


class LeadDoctor(Base):
    """Lead doctor profile scraped/imported from external platforms.

    All fields are nullable TEXT to handle the variable quality of
    externally sourced data. The ``id`` column is an auto-incrementing
    integer primary key.
    """

    __tablename__ = "lead_doctors"

    # ── Primary key ──────────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # ── Core profile fields ──────────────────────────────────────────────
    city: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    speciality: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    doctor_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    qualification: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialization: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    fee: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Location / Hospital ──────────────────────────────────────────────
    location: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    hospital_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    hospital_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Credentials & Recognition ────────────────────────────────────────
    awards: Mapped[str | None] = mapped_column(Text, nullable=True)
    memberships: Mapped[str | None] = mapped_column(Text, nullable=True)
    registrations: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Services & Profile ───────────────────────────────────────────────
    services: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ── Composite indexes for common query patterns ──────────────────────
    __table_args__ = (
        # Filters: "all dentists in Mumbai"
        Index("ix_lead_doctors_city_speciality", "city", "speciality"),
        # Filters: "all doctors at Apollo in Bangalore"
        Index("ix_lead_doctors_city_hospital", "city", "hospital_name"),
        # Filters: "all cardiologists at a specific location"
        Index("ix_lead_doctors_speciality_location", "speciality", "location"),
    )

    def __repr__(self) -> str:
        return (
            f"<LeadDoctor(id={self.id}, name={self.doctor_name!r}, "
            f"city={self.city!r}, speciality={self.speciality!r})>"
        )
