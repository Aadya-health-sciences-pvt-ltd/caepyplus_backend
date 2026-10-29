"""Pydantic shapes for workspace doctor dashboard appointment JSON."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..glance_shapes import TODAYS_SCHEDULE_KEY, empty_todays_schedule
from ..models.enums import AppointmentType, ConsultationType


class WorkspaceAppointmentItem(BaseModel):
    """One patient appointment inside ``appointment_json.todays_schedule``."""

    model_config = ConfigDict(use_enum_values=True)

    patient_meta_code: str = Field(..., max_length=255)
    appointment_type: AppointmentType
    patient_name: str = Field(..., max_length=255)
    first_name: str = Field(..., max_length=255)
    last_name: str = Field(..., max_length=255)
    consultation_type: ConsultationType
    time_slot: str = Field(..., max_length=255)


class AppointmentJsonDocument(BaseModel):
    """Stored ``appointment_json`` / glance ``appointments`` shape (DRY with service)."""

    todays_schedule: list[WorkspaceAppointmentItem] = Field(
        default_factory=list,
        description=f"Patient list under key ``{TODAYS_SCHEDULE_KEY}``",
    )

    @classmethod
    def empty(cls) -> AppointmentJsonDocument:
        return cls.model_validate(empty_todays_schedule())

