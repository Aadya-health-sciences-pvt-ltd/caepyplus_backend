"""Linq360 dashboard models (schema ``linq360``)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from ...db.session import Base
from .enums import AppointmentType, ConsultationType


class WorkspaceDoctorDashboard(Base):
    """Workspace-level doctor dashboard appointment row (schema ``linq360``)."""

    __tablename__ = "workspace_doctor_dashboard"
    __table_args__ = {"schema": "linq360"}

    appointment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_meta_code: Mapped[str] = mapped_column(String(255), nullable=False)
    appointment_type: Mapped[AppointmentType] = mapped_column(
        SQLEnum(
            AppointmentType,
            name="linq360_appointment_type",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    patient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    consultation_type: Mapped[ConsultationType] = mapped_column(
        SQLEnum(
            ConsultationType,
            name="linq360_consultation_type",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    time_slot: Mapped[str] = mapped_column(String(255), nullable=False)
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
