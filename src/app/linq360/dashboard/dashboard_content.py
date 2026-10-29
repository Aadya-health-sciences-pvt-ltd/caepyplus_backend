"""Pending content block helpers for doctor_dashboard.todays_glance."""
from __future__ import annotations

from typing import Any

from ..services.practice_hub_pending_client import (
    PENDING_SOURCES,
    parse_source_block,
    pending_count_from_block,
)


def payload_from_stored_content(existing: dict[str, Any] | None) -> dict[str, Any]:
    """Read source blocks from doctor_dashboard.todays_glance (content-only)."""
    raw = existing if isinstance(existing, dict) else {}
    nested = raw.get("content")
    if isinstance(nested, dict) and any(key in nested for key in PENDING_SOURCES):
        content = nested
    elif any(key in raw for key in PENDING_SOURCES):
        content = raw
    else:
        content = nested if isinstance(nested, dict) else raw
    content = content if isinstance(content, dict) else {}
    return {source: content.get(source) or {} for source in PENDING_SOURCES}


def counts_from_glance(existing: dict[str, Any] | None) -> dict[str, int]:
    payload = payload_from_stored_content(existing)
    return {
        source: pending_count_from_block(payload.get(source)) for source in PENDING_SOURCES
    }


def content_block(payload: dict[str, Any]) -> dict[str, Any]:
    block: dict[str, Any] = {}
    total = 0
    for source in PENDING_SOURCES:
        entry = parse_source_block(source, payload.get(source))
        block[source] = entry
        total += int(entry["pending_count"])
    block["total_pending_counts"] = total
    return block
