"""Dashboard realtime: event map, debounce, refresh, WebSocket hub."""
from .debounce import get_debounce_coordinator, reset_debounce_coordinator_for_tests
from .event_map import (
    DashboardSection,
    group_key,
    room_name,
    sections_for_event,
    ws_event_name,
)
from .refresh_service import enqueue_dashboard_event, ensure_debounce_wired
from .ws_hub import get_dashboard_ws_hub, reset_dashboard_ws_hub_for_tests

__all__ = [
    "DashboardSection",
    "enqueue_dashboard_event",
    "ensure_debounce_wired",
    "get_dashboard_ws_hub",
    "get_debounce_coordinator",
    "group_key",
    "reset_dashboard_ws_hub_for_tests",
    "reset_debounce_coordinator_for_tests",
    "room_name",
    "sections_for_event",
    "ws_event_name",
]
