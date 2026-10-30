"""Webhook event → dashboard section mapping; group by ws_user_id + workspace_id."""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable


class DashboardSection(StrEnum):
    APPOINTMENTS = "appointments"
    REQUESTS = "requests"
    CONTENT = "content"
    PAYMENTS = "payments"


# Canonical event names → sections that must refresh.
EVENT_SECTION_MAP: dict[str, frozenset[DashboardSection]] = {
    "appointment.created": frozenset({DashboardSection.APPOINTMENTS}),
    "appointment.updated": frozenset({DashboardSection.APPOINTMENTS}),
    "appointment.cancelled": frozenset({DashboardSection.APPOINTMENTS}),
    "appointment.completed": frozenset({DashboardSection.APPOINTMENTS}),
    "request.created": frozenset({DashboardSection.REQUESTS}),
    "request.accepted": frozenset({DashboardSection.REQUESTS}),
    "request.rejected": frozenset({DashboardSection.REQUESTS}),
    "review.created": frozenset({DashboardSection.CONTENT}),
    "review.updated": frozenset({DashboardSection.CONTENT}),
    "comment.created": frozenset({DashboardSection.CONTENT}),
    "comment.updated": frozenset({DashboardSection.CONTENT}),
    "blog_comment.created": frozenset({DashboardSection.CONTENT}),
    "podcast_comment.created": frozenset({DashboardSection.CONTENT}),
    "payment.created": frozenset({DashboardSection.PAYMENTS}),
    "payment.updated": frozenset({DashboardSection.PAYMENTS}),
    # Full dashboard push (existing appointment-system webhook).
    "dashboard.snapshot": frozenset(
        {
            DashboardSection.APPOINTMENTS,
            DashboardSection.REQUESTS,
        }
    ),
}


def group_key(ws_user_id: int, workspace_id: int) -> tuple[int, int]:
    """Debounce / WebSocket grouping key."""
    return (int(ws_user_id), int(workspace_id))


def room_name(ws_user_id: int, workspace_id: int) -> str:
    """Authorized WebSocket room for a doctor workspace."""
    return f"dashboard:{int(workspace_id)}:{int(ws_user_id)}"


def sections_for_event(event_type: str | None) -> frozenset[DashboardSection]:
    """Resolve which dashboard sections an event affects."""
    if not event_type or not str(event_type).strip():
        return EVENT_SECTION_MAP["dashboard.snapshot"]
    key = str(event_type).strip().lower()
    return EVENT_SECTION_MAP.get(key, EVENT_SECTION_MAP["dashboard.snapshot"])


def merge_sections(
    *groups: Iterable[DashboardSection],
) -> frozenset[DashboardSection]:
    out: set[DashboardSection] = set()
    for group in groups:
        out.update(group)
    return frozenset(out)


def ws_event_name(sections: Iterable[DashboardSection]) -> str:
    """Pick a primary WS event name from affected sections."""
    section_set = set(sections)
    if section_set == {DashboardSection.APPOINTMENTS}:
        return "appointments_updated"
    if section_set == {DashboardSection.REQUESTS}:
        return "requests_updated"
    if section_set == {DashboardSection.CONTENT}:
        return "content_counts_updated"
    if section_set == {DashboardSection.PAYMENTS}:
        return "payments_updated"
    return "dashboard_updated"
