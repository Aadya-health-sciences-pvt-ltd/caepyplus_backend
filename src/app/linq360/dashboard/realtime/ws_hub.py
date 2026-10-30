"""In-process dashboard WebSocket room hub (single instance)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from .event_map import DashboardSection, room_name, ws_event_name

logger = logging.getLogger(__name__)


class DashboardWsHub:
    """Track sockets per ``dashboard:{workspace_id}:{ws_user_id}`` room."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        *,
        ws_user_id: int,
        workspace_id: int,
    ) -> str:
        await websocket.accept()
        name = room_name(ws_user_id, workspace_id)
        self._rooms.setdefault(name, set()).add(websocket)
        logger.info("dashboard_ws_join room=%s", name)
        return name

    def disconnect(self, websocket: WebSocket, room: str) -> None:
        members = self._rooms.get(room)
        if not members:
            return
        members.discard(websocket)
        if not members:
            self._rooms.pop(room, None)
        logger.info("dashboard_ws_leave room=%s", room)

    async def publish(
        self,
        *,
        ws_user_id: int,
        workspace_id: int,
        sections: set[DashboardSection] | frozenset[DashboardSection],
        snapshot: dict[str, Any] | None = None,
    ) -> int:
        name = room_name(ws_user_id, workspace_id)
        members = list(self._rooms.get(name, set()))
        if not members:
            return 0
        payload = {
            "event": ws_event_name(sections),
            "ws_user_id": int(ws_user_id),
            "workspace_id": int(workspace_id),
            "sections": sorted(s.value for s in sections),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": snapshot,
        }
        dead: list[WebSocket] = []
        sent = 0
        for ws in members:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, name)
        logger.info(
            "dashboard_ws_publish room=%s event=%s recipients=%s",
            name,
            payload["event"],
            sent,
        )
        return sent


_hub: DashboardWsHub | None = None


def get_dashboard_ws_hub() -> DashboardWsHub:
    global _hub
    if _hub is None:
        _hub = DashboardWsHub()
    return _hub


def reset_dashboard_ws_hub_for_tests() -> None:
    global _hub
    _hub = None
