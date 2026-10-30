"""In-memory debounce coordinator (single-instance). Redis optional later."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar

from .event_map import DashboardSection, group_key

logger = logging.getLogger(__name__)

T = TypeVar("T")
RefreshCallback = Callable[
    [int, int, frozenset[DashboardSection], dict[str, Any]],
    Awaitable[None],
]


class InMemoryDebounceCoordinator:
    """Coalesce events per ``(ws_user_id, workspace_id)`` for ``window_ms``.

    - New events in the window reset the timer and merge sections.
    - If a refresh is already running for the key, sections are queued for a follow-up.
    """

    def __init__(self, window_ms: int = 2000) -> None:
        self.window_s = max(window_ms, 0) / 1000.0
        self._pending_sections: dict[tuple[int, int], set[DashboardSection]] = {}
        self._pending_context: dict[tuple[int, int], dict[str, Any]] = {}
        self._timers: dict[tuple[int, int], asyncio.Task[None]] = {}
        self._running: set[tuple[int, int]] = set()
        self._follow_up: dict[tuple[int, int], set[DashboardSection]] = {}
        self._follow_up_context: dict[tuple[int, int], dict[str, Any]] = {}
        self._callback: RefreshCallback | None = None

    def configure(self, *, window_ms: int | None = None) -> None:
        if window_ms is not None:
            self.window_s = max(int(window_ms), 0) / 1000.0

    def set_callback(self, callback: RefreshCallback) -> None:
        self._callback = callback

    def schedule(
        self,
        *,
        ws_user_id: int,
        workspace_id: int,
        sections: Iterable[DashboardSection],
        context: dict[str, Any] | None = None,
    ) -> None:
        key = group_key(ws_user_id, workspace_id)
        section_set = set(sections)
        ctx = dict(context or {})

        if key in self._running:
            self._follow_up.setdefault(key, set()).update(section_set)
            self._follow_up_context[key] = {
                **self._follow_up_context.get(key, {}),
                **ctx,
            }
            logger.info(
                "debounce_follow_up key=%s sections=%s",
                key,
                sorted(s.value for s in section_set),
            )
            return

        self._pending_sections.setdefault(key, set()).update(section_set)
        self._pending_context[key] = {**self._pending_context.get(key, {}), **ctx}

        existing = self._timers.get(key)
        if existing and not existing.done():
            existing.cancel()

        self._timers[key] = asyncio.create_task(
            self._fire_after_window(key),
            name=f"dashboard-debounce-{key[0]}-{key[1]}",
        )
        logger.info(
            "debounce_scheduled key=%s window_s=%s sections=%s",
            key,
            self.window_s,
            sorted(s.value for s in self._pending_sections[key]),
        )

    async def _fire_after_window(self, key: tuple[int, int]) -> None:
        if self.window_s > 0:
            try:
                await asyncio.sleep(self.window_s)
            except asyncio.CancelledError:
                return

        sections = frozenset(self._pending_sections.pop(key, set()))
        context = self._pending_context.pop(key, {})
        self._timers.pop(key, None)
        if not sections or self._callback is None:
            return

        self._running.add(key)
        try:
            await self._callback(key[0], key[1], sections, context)
        except Exception:
            logger.exception("debounce_refresh_failed key=%s", key)
        finally:
            self._running.discard(key)

        follow = self._follow_up.pop(key, None)
        follow_ctx = self._follow_up_context.pop(key, {})
        if follow:
            self.schedule(
                ws_user_id=key[0],
                workspace_id=key[1],
                sections=follow,
                context=follow_ctx,
            )


_coordinator: InMemoryDebounceCoordinator | None = None


def get_debounce_coordinator() -> InMemoryDebounceCoordinator:
    global _coordinator
    if _coordinator is None:
        from ....core.config import get_settings

        settings = get_settings()
        window = getattr(settings, "DEBOUNCE_WINDOW_MS", 2000)
        _coordinator = InMemoryDebounceCoordinator(window_ms=int(window))
    return _coordinator


def reset_debounce_coordinator_for_tests() -> None:
    """Clear singleton (tests only)."""
    global _coordinator
    _coordinator = None
