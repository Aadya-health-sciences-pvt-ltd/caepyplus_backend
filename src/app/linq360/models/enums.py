"""Linq360 domain enums for dashboard tables."""
from __future__ import annotations

from enum import Enum


class AppointmentType(str, Enum):
    """Appointment / request kind on the workspace doctor dashboard."""

    REQUEST = "REQUEST"
    BOOKING = "BOOKING"
    CALL = "CALL"


class ConsultationType(str, Enum):
    """Consultation mode for a workspace appointment."""

    IN_PERSON = "in-person"
    TELECONSULTATION = "teleconsultation"
