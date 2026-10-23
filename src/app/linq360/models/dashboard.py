"""Linq360 dashboard models (schema ``linq360``)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column

from ...db.session import Base


class WorkspaceDoctorDashboard(Base):
    """Workspace-level doctor dashboard appointment row (schema ``linq360``).

    Column order:
    appointment_id, appointment_json, workspace_id, ws_user_id, ph_user_id, todays_glance
    """

    __tablename__ = "workspace_doctor_dashboard"
    __table_args__ = {"schema": "linq360"}

    appointment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appointment_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    workspace_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Portal workspace user from select token (``user_id`` claim, e.g. 325).
    ws_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Practice Hub / Drupal doctor uid (``appointment_doctor_id``, e.g. 892).
    ph_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    todays_glance: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )


class DoctorDashboard(Base):
    """Doctor dashboard row (schema ``linq360``).

    Step 1 scaffold: primary key only. Business columns come later.
    """

    __tablename__ = "doctor_dashboard"
    __table_args__ = {"schema": "linq360"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
