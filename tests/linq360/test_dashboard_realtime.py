"""Realtime dashboard: event map, debounce coalescing, WS room key."""
from __future__ import annotations

import asyncio

import pytest

from src.app.linq360.dashboard.realtime.debounce import (
    InMemoryDebounceCoordinator,
    reset_debounce_coordinator_for_tests,
)
from src.app.linq360.dashboard.realtime.event_map import (
    DashboardSection,
    group_key,
    room_name,
    sections_for_event,
    ws_event_name,
)
from src.app.linq360.dashboard.realtime.ws_hub import (
    reset_dashboard_ws_hub_for_tests,
)


def test_sections_for_event_mapping() -> None:
    assert sections_for_event("appointment.created") == frozenset(
        {DashboardSection.APPOINTMENTS}
    )
    assert sections_for_event("request.created") == frozenset(
        {DashboardSection.REQUESTS}
    )
    assert sections_for_event("review.created") == frozenset(
        {DashboardSection.CONTENT}
    )
    assert DashboardSection.APPOINTMENTS in sections_for_event(None)
    assert DashboardSection.REQUESTS in sections_for_event("")


def test_group_and_room_key() -> None:
    assert group_key(325, 161) == (325, 161)
    assert room_name(325, 161) == "dashboard:161:325"
    assert ws_event_name({DashboardSection.CONTENT}) == "content_counts_updated"
    assert ws_event_name(
        {DashboardSection.APPOINTMENTS, DashboardSection.REQUESTS}
    ) == "dashboard_updated"


@pytest.mark.asyncio
async def test_debounce_coalesces_same_group() -> None:
    reset_debounce_coordinator_for_tests()
    calls: list[tuple[int, int, frozenset[DashboardSection]]] = []

    async def _cb(
        ws_user_id: int,
        workspace_id: int,
        sections: frozenset[DashboardSection],
        context: dict,
    ) -> None:
        calls.append((ws_user_id, workspace_id, sections))

    coord = InMemoryDebounceCoordinator(window_ms=50)
    coord.set_callback(_cb)
    coord.schedule(
        ws_user_id=325,
        workspace_id=161,
        sections={DashboardSection.APPOINTMENTS},
    )
    coord.schedule(
        ws_user_id=325,
        workspace_id=161,
        sections={DashboardSection.REQUESTS},
    )
    await asyncio.sleep(0.12)
    assert len(calls) == 1
    assert calls[0][0] == 325
    assert calls[0][1] == 161
    assert calls[0][2] == frozenset(
        {DashboardSection.APPOINTMENTS, DashboardSection.REQUESTS}
    )


@pytest.mark.asyncio
async def test_debounce_isolates_different_groups() -> None:
    calls: list[tuple[int, int]] = []

    async def _cb(
        ws_user_id: int,
        workspace_id: int,
        sections: frozenset[DashboardSection],
        context: dict,
    ) -> None:
        calls.append((ws_user_id, workspace_id))

    coord = InMemoryDebounceCoordinator(window_ms=30)
    coord.set_callback(_cb)
    coord.schedule(
        ws_user_id=1,
        workspace_id=10,
        sections={DashboardSection.APPOINTMENTS},
    )
    coord.schedule(
        ws_user_id=2,
        workspace_id=10,
        sections={DashboardSection.APPOINTMENTS},
    )
    await asyncio.sleep(0.1)
    assert sorted(calls) == [(1, 10), (2, 10)]


@pytest.mark.asyncio
async def test_follow_up_when_refresh_running() -> None:
    order: list[str] = []
    gate = asyncio.Event()

    async def _cb(
        ws_user_id: int,
        workspace_id: int,
        sections: frozenset[DashboardSection],
        context: dict,
    ) -> None:
        order.append("start:" + ",".join(sorted(s.value for s in sections)))
        if "appointments" in {s.value for s in sections}:
            await gate.wait()
        order.append("end:" + ",".join(sorted(s.value for s in sections)))

    coord = InMemoryDebounceCoordinator(window_ms=0)
    coord.set_callback(_cb)
    coord.schedule(
        ws_user_id=325,
        workspace_id=161,
        sections={DashboardSection.APPOINTMENTS},
    )
    await asyncio.sleep(0.02)
    coord.schedule(
        ws_user_id=325,
        workspace_id=161,
        sections={DashboardSection.CONTENT},
    )
    gate.set()
    await asyncio.sleep(0.05)
    assert any(x.startswith("start:appointments") for x in order)
    assert any("content" in x for x in order)


def teardown_function() -> None:
    reset_debounce_coordinator_for_tests()
    reset_dashboard_ws_hub_for_tests()
