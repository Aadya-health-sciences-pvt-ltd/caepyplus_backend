"""Pydantic shapes for workspace doctor dashboard appointment JSON."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..models.enums import AppointmentType, ConsultationType


class WorkspaceAppointmentItem(BaseModel):
    """One appointment object inside ``appointments_json``."""

    model_config = ConfigDict(use_enum_values=True)

    patient_meta_code: str = Field(..., max_length=255)
    appointment_type: AppointmentType
    patient_name: str = Field(..., max_length=255)
    first_name: str = Field(..., max_length=255)
    last_name: str = Field(..., max_length=255)
    consultation_type: ConsultationType
    time_slot: str = Field(..., max_length=255)


class WorkspaceAppointmentsPayload(BaseModel):
    """Array of appointments stored in ``appointments_json``."""

    appointments: list[WorkspaceAppointmentItem] = Field(default_factory=list)
