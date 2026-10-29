"""Linq360 dashboard models (schema ``linq360``)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...db.session import Base
from ..glance_shapes import empty_todays_schedule


class WorkspaceDoctorDashboard(Base):
    """Workspace-level doctor dashboard row (schema ``linq360``).

    One row per ``(ws_user_id, ph_user_id, workspace_id)``.

    Same portal user + doctor + workspace → upsert.
    Same portal user + doctor + different workspace → new row
    (a doctor can work in multiple workspaces).

    Column order:
    appointment_id, ph_user_id, ws_user_id, workspace_id,
    appointments, requests, appointment_json

    ``appointment_json`` shape: ``{ "todays_schedule": [ ...patient objects ] }``.
    Pending content lives on ``DoctorDashboard.todays_glance``, not here.
    """

    __tablename__ = "workspace_doctor_dashboard"
    __table_args__ = (
        UniqueConstraint(
            "ws_user_id",
            "ph_user_id",
            "workspace_id",
            name="uq_workspace_doctor_dashboard_ws_ph_workspace",
        ),
        {"schema": "linq360"},
    )

    appointment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Practice Hub / Drupal doctor uid (``appointment_doctor_id``, e.g. 892).
    ph_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Portal workspace user from select token (``user_id`` claim, e.g. 325).
    ws_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    workspace_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    appointments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    requests: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    appointment_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=empty_todays_schedule,
    )


class DoctorDashboard(Base):
    """Doctor-level dashboard (schema ``linq360``).

    Holds Today-at-a-Glance **pending content** only (reviews / blog / podcast).
    """

    __tablename__ = "doctor_dashboard"
    __table_args__ = {"schema": "linq360"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Practice Hub / Drupal doctor uid — unique glance key.
    ph_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True, index=True)
    # Portal user from workspace select token.
    ws_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Content block only (not wrapped in {"content": ...}).
    todays_glance: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
