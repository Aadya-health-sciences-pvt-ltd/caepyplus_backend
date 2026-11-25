"""Linq360 domain enums for dashboard tables."""
from __future__ import annotations

from enum import Enum


class AppointmentType(str, Enum):
    REQUEST = "REQUEST"
    BOOKING = "BOOKING"
    CALL = "CALL"
    WALK_IN = "WALK_IN"


class ConsultationType(str, Enum):

    IN_PERSON = "in-person"
    TELECONSULTATION = "teleconsultation"
