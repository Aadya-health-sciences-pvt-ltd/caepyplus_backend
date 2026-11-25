"""In-app clear of workspace_doctor_dashboard (env: ENABLED / AT_AT / CLEAR_TZ)."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...core.config import Settings, get_settings
from ...db.session import get_db_manager
from .config.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_clear_task: asyncio.Task[None] | None = None


def parse_clear_hhmm(value: str) -> tuple[int, int]:
    """Parse HH:MM → (hour, minute)."""
    raw = (value or "").strip()
    match = _HHMM_RE.match(raw)
    if not match:
        raise ValueError(f"Invalid CLEAR_AT {value!r}; expected HH:MM")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f"Invalid CLEAR_AT {value!r}; hour 0-23, minute 0-59")
    return hour, minute


def resolve_clear_tz(name: str) -> timezone | ZoneInfo:
    """Resolve IANA timezone; Asia/Kolkata falls back to UTC+05:30 if tzdata missing."""
    key = (name or "").strip() or "Asia/Kolkata"
    try:
        return ZoneInfo(key)
    except ZoneInfoNotFoundError:
        if key in {"Asia/Kolkata", "Asia/Calcutta"}:
            return timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        raise ValueError(f"Invalid CLEAR_TZ {name!r}") from None


def next_clear_datetime(
    *,
    now: datetime,
    hour: int,
    minute: int,
    tz: timezone | ZoneInfo,
) -> datetime:
    """Next clear time in ``tz`` (rolls to tomorrow if already past today)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local_now = now.astimezone(tz)
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate = candidate + timedelta(days=1)
    return candidate


async def _run_clear_once() -> int:
    db_manager = get_db_manager()
    async with db_manager.session() as session:
        return await DashboardService(session).clear_all_workspace_dashboards()


async def _clear_loop(settings: Settings) -> None:
    try:
        hour, minute = parse_clear_hhmm(settings.LINQ360_DASHBOARD_CLEAR_AT)
        tz = resolve_clear_tz(settings.LINQ360_DASHBOARD_CLEAR_TZ)
    except ValueError as exc:
        logger.error("linq360_dashboard_clear_config_invalid err=%s", exc)
        return

    logger.info(
        "linq360_dashboard_clear_scheduler_started at=%s tz=%s",
        settings.LINQ360_DASHBOARD_CLEAR_AT,
        settings.LINQ360_DASHBOARD_CLEAR_TZ,
    )
    last_cleared_on: date | None = None

    while True:
        try:
            now = datetime.now(timezone.utc)
            target = next_clear_datetime(now=now, hour=hour, minute=minute, tz=tz)
            delay = max(0.0, (target - now.astimezone(timezone.utc)).total_seconds())
            logger.info(
                "linq360_dashboard_clear_next_run at=%s delay_s=%.0f",
                target.isoformat(),
                delay,
            )
            await asyncio.sleep(delay)

            run_day = target.astimezone(tz).date()
            if last_cleared_on == run_day:
                await asyncio.sleep(1.0)
                continue

            deleted = await _run_clear_once()
            last_cleared_on = run_day
            logger.info(
                "linq360_dashboard_clear_ran deleted=%s day=%s",
                deleted,
                run_day.isoformat(),
            )
        except asyncio.CancelledError:
            logger.info("linq360_dashboard_clear_scheduler_stopped")
            raise
        except Exception:
            logger.exception("linq360_dashboard_clear_scheduler_error")
            await asyncio.sleep(60.0)


def start_workspace_dashboard_clear_scheduler(
    settings: Settings | None = None,
) -> asyncio.Task[None] | None:
    """Start clear loop when ENABLED; otherwise no-op."""
    global _clear_task
    cfg = settings or get_settings()
    if not cfg.LINQ360_DASHBOARD_CLEAR_ENABLED:
        logger.info("linq360_dashboard_clear_scheduler_disabled")
        return None
    if _clear_task is not None and not _clear_task.done():
        return _clear_task
    _clear_task = asyncio.create_task(
        _clear_loop(cfg),
        name="linq360_workspace_dashboard_clear",
    )
    return _clear_task


async def stop_workspace_dashboard_clear_scheduler() -> None:
    """Stop clear loop on shutdown."""
    global _clear_task
    task = _clear_task
    _clear_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
