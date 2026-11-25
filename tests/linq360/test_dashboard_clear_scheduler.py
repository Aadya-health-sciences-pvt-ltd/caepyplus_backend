"""Unit tests for LinQ360 in-app dashboard clear schedule helpers."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.app.linq360.dashboard.clear_scheduler import (
    next_clear_datetime,
    parse_clear_hhmm,
    resolve_clear_tz,
)


def test_parse_clear_hhmm_ok() -> None:
    assert parse_clear_hhmm("00:00") == (0, 0)
    assert parse_clear_hhmm("9:05") == (9, 5)
    assert parse_clear_hhmm("23:59") == (23, 59)


def test_parse_clear_hhmm_invalid() -> None:
    with pytest.raises(ValueError):
        parse_clear_hhmm("24:00")
    with pytest.raises(ValueError):
        parse_clear_hhmm("12")
    with pytest.raises(ValueError):
        parse_clear_hhmm("12:60")


def test_resolve_clear_tz_defaultish() -> None:
    assert resolve_clear_tz("Asia/Kolkata").key == "Asia/Kolkata"


def test_resolve_clear_tz_invalid() -> None:
    with pytest.raises(ValueError):
        resolve_clear_tz("Not/AZone")


def test_next_clear_datetime_same_day_when_before() -> None:
    tz = ZoneInfo("Asia/Kolkata")
    now = datetime(2026, 11, 25, 10, 0, tzinfo=tz)
    nxt = next_clear_datetime(now=now, hour=12, minute=12, tz=tz)
    assert nxt == datetime(2026, 11, 25, 12, 12, tzinfo=tz)


def test_next_clear_datetime_rolls_to_tomorrow_when_past() -> None:
    tz = ZoneInfo("Asia/Kolkata")
    now = datetime(2026, 11, 25, 12, 13, tzinfo=tz)
    nxt = next_clear_datetime(now=now, hour=12, minute=12, tz=tz)
    assert nxt == datetime(2026, 11, 26, 12, 12, tzinfo=tz)
