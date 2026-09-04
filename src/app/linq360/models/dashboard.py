"""Linq360 dashboard models (schema ``linq360``)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column

from ...db.session import Base


class WorkspaceDoctorDashboard(Base):
    """Workspace-level doctor dashboard appointment row (schema ``linq360``)."""

    __tablename__ = "workspace_doctor_dashboard"
    __table_args__ = {"schema": "linq360"}

    appointment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    appointments_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )


class DoctorDashboard(Base):
    """Doctor dashboard row (schema ``linq360``).

    Step 1 scaffold: primary key only. Business columns come later.
    """

    __tablename__ = "doctor_dashboard"
    __table_args__ = {"schema": "linq360"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
