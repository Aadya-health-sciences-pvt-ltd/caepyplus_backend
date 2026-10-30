"""After debounce: refresh affected dashboard sections, upsert, publish WS."""
from __future__ import annotations

import logging
from typing import Any

from ....db.session import get_db_manager
from ...services.practice_hub_pending_client import fetch_pending_counts
from ..config.dashboard_service import DashboardService
from .debounce import get_debounce_coordinator
from .event_map import DashboardSection
from .ws_hub import get_dashboard_ws_hub

logger = logging.getLogger(__name__)


async def run_debounced_refresh(
    ws_user_id: int,
    workspace_id: int,
    sections: frozenset[DashboardSection],
    context: dict[str, Any],
) -> None:
    """Refresh only requested sections for one group key, then notify WS."""
    ph_user_id = context.get("ph_user_id")
    if ph_user_id is None:
        logger.warning(
            "debounce_refresh_skip missing ph_user_id ws_user_id=%s workspace_id=%s",
            ws_user_id,
            workspace_id,
        )
        return

    token = context.get("authorization")
    db_manager = get_db_manager()
    async with db_manager.session() as session:
        svc = DashboardService(session)
        uid = str(ph_user_id)

        if DashboardSection.APPOINTMENTS in sections or DashboardSection.REQUESTS in sections:
            # Prefer authoritative snapshot from webhook when present.
            if any(
                k in context
                for k in ("appointments", "requests", "todays_schedule")
            ):
                await svc.upsert_workspace_schedule(
                    ph_user_id=int(ph_user_id),
                    workspace_id=int(workspace_id),
                    ws_user_id=int(ws_user_id),
                    appointments=int(context.get("appointments") or 0),
                    requests=int(context.get("requests") or 0),
                    todays_schedule=context.get("todays_schedule") or [],
                )

        if DashboardSection.CONTENT in sections and token:
            await svc.upsert_pending_glance(
                uid,
                await fetch_pending_counts(token),
                workspace_id=int(workspace_id),
                ws_user_id=int(ws_user_id),
            )
        elif DashboardSection.CONTENT in sections and token is None:
            logger.info(
                "content_refresh_skipped_no_token ws_user_id=%s workspace_id=%s",
                ws_user_id,
                workspace_id,
            )

        # payments: no external source yet — glance always returns {}

        snapshot = await svc.get_glance(
            uid,
            workspace_id=int(workspace_id),
            ws_user_id=int(ws_user_id),
        )

    await get_dashboard_ws_hub().publish(
        ws_user_id=int(ws_user_id),
        workspace_id=int(workspace_id),
        sections=sections,
        snapshot=snapshot,
    )


def ensure_debounce_wired() -> None:
    """Attach refresh callback to the process-wide debounce coordinator."""
    coordinator = get_debounce_coordinator()
    coordinator.set_callback(run_debounced_refresh)


def enqueue_dashboard_event(
    *,
    ws_user_id: int,
    workspace_id: int,
    sections: frozenset[DashboardSection] | set[DashboardSection],
    context: dict[str, Any] | None = None,
) -> None:
    """Public entry: schedule a debounced refresh for a group key."""
    ensure_debounce_wired()
    get_debounce_coordinator().schedule(
        ws_user_id=int(ws_user_id),
        workspace_id=int(workspace_id),
        sections=sections,
        context=context,
    )
