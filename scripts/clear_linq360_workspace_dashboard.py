#!/usr/bin/env python3
"""Clear linq360.workspace_doctor_dashboard (today-only appointment snapshots).

Schedule at 00:00 Asia/Kolkata so yesterday's schedule cannot linger.
Does not touch linq360.doctor_dashboard. Refill comes from the next full
webhook snapshot (POST /webhooks/dashboard).

Usage
-----
    python scripts/clear_linq360_workspace_dashboard.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.app.db.session import get_db_manager  # noqa: E402
from src.app.linq360.dashboard.config.dashboard_service import (  # noqa: E402
    DashboardService,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _run() -> int:
    db_manager = get_db_manager()
    try:
        async with db_manager.session() as session:
            deleted = await DashboardService(session).clear_all_workspace_dashboards()
        logger.info("clear complete deleted=%s", deleted)
        return 0
    finally:
        await db_manager.close()


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_run()))
    except Exception:
        logger.exception("clear_linq360_workspace_dashboard failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
