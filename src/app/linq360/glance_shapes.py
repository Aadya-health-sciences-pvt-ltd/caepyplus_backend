"""Single source of truth for LinQ360 glance / appointment_json shapes (DRY).

No imports from ``services`` — keeps model/schema import graphs acyclic.
"""
from __future__ import annotations

from typing import Any

# Keys
TODAYS_SCHEDULE_KEY = "todays_schedule"
GLANCE_CONTENT_KEY = "content"
GLANCE_APPOINTMENTS_KEY = "appointments"
GLANCE_REQUESTS_KEY = "requests"
GLANCE_PAYMENTS_KEY = "payments"

# Top-level glance response keys (API contract).
GLANCE_RESPONSE_KEYS = (
    GLANCE_CONTENT_KEY,
    GLANCE_APPOINTMENTS_KEY,
    GLANCE_REQUESTS_KEY,
    GLANCE_PAYMENTS_KEY,
)


def empty_todays_schedule() -> dict[str, list[Any]]:
    """Empty ``appointment_json`` / glance ``appointments`` document."""
    return {TODAYS_SCHEDULE_KEY: []}


def normalize_todays_schedule(appointment_json: object) -> dict[str, list[Any]]:
    """Normalize stored JSON to ``{ "todays_schedule": [ ... ] }``.

    Accepts:
    - already-wrapped ``{ todays_schedule: [...] }``
    - bare list of patients
    - legacy flat single patient object
    - null / empty → empty schedule
    """
    if appointment_json is None:
        return empty_todays_schedule()

    if isinstance(appointment_json, list):
        return {
            TODAYS_SCHEDULE_KEY: [
                item for item in appointment_json if isinstance(item, dict)
            ]
        }

    if not isinstance(appointment_json, dict):
        return empty_todays_schedule()

    schedule = appointment_json.get(TODAYS_SCHEDULE_KEY)
    if isinstance(schedule, list):
        return {
            TODAYS_SCHEDULE_KEY: [item for item in schedule if isinstance(item, dict)]
        }

    # Legacy flat patient object.
    if appointment_json.get("patient_meta_code") is not None:
        return {TODAYS_SCHEDULE_KEY: [dict(appointment_json)]}

    return empty_todays_schedule()


def card_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def merge_glance_response(
    content: dict[str, Any],
    *,
    requests: object = None,
    appointment_json: object = None,
) -> dict[str, Any]:
    """One glance document for sync and get (``content`` already built)."""
    return {
        GLANCE_CONTENT_KEY: content,
        GLANCE_REQUESTS_KEY: card_dict(requests),
        GLANCE_APPOINTMENTS_KEY: normalize_todays_schedule(appointment_json),
        GLANCE_PAYMENTS_KEY: {},
    }


def workspace_id_or_zero(workspace_id: int | None) -> int:
    return int(workspace_id) if workspace_id is not None else 0
