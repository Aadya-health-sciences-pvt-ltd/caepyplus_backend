"""Fetch Drupal pending counts from Practice Hub.

GET {LINQMD_PRACTICE_HUB_API_URL}/api/linq360/pending-counts/{user_id}
"""
from __future__ import annotations

from typing import Any

import httpx

from ...core.config import get_settings


class PracticeHubPendingError(Exception):
    """Practice Hub pending-counts call failed."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


PENDING_SOURCES = ("reviews", "blog_comments", "podcast_comments")
GLANCE_CARDS = ("appointments", "requests", "payments")


def non_negative_int(value: object) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def pending_count_from_block(block: object) -> int:
    if isinstance(block, dict):
        return non_negative_int(block.get("pending_count"))
    return 0


def parse_pending_counts(body: dict[str, Any]) -> dict[str, int]:
    """Map the Practice Hub payload to the three pending counts.

    ``total_pending_counts`` from Drupal is ignored. CAEPY sums the three counts.
    """
    return {source: pending_count_from_block(body.get(source)) for source in PENDING_SOURCES}


async def fetch_pending_counts(linqmd_user_id: str) -> dict[str, int]:
    """GET Practice Hub pending counts for a Drupal uid."""
    settings = get_settings()
    base = (settings.LINQMD_PRACTICE_HUB_API_URL or "").strip()
    if not base:
        raise PracticeHubPendingError("LINQMD_PRACTICE_HUB_API_URL is not set")

    uid = str(linqmd_user_id).strip()
    url = settings.linqmd_practice_hub_url(f"/api/linq360/pending-counts/{uid}")
    headers: dict[str, str] = {"Accept": "application/json"}
    if settings.LINQMD_PRACTICE_HUB_AUTH_TOKEN:
        headers["Authorization"] = settings.LINQMD_PRACTICE_HUB_AUTH_TOKEN
    if settings.LINQMD_PRACTICE_HUB_COOKIE:
        headers["Cookie"] = settings.LINQMD_PRACTICE_HUB_COOKIE

    try:
        async with httpx.AsyncClient(timeout=settings.LINQMD_API_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise PracticeHubPendingError(f"Practice Hub pending-counts request failed: {exc}") from exc

    if response.status_code != 200:
        detail = response.text[:300]
        raise PracticeHubPendingError(
            f"Practice Hub pending-counts HTTP {response.status_code}: {detail}",
            status_code=response.status_code,
        )

    try:
        body = response.json()
    except Exception as exc:
        raise PracticeHubPendingError("Practice Hub pending-counts response was not JSON") from exc
    if not isinstance(body, dict):
        raise PracticeHubPendingError("Practice Hub pending-counts response was not an object")
    return parse_pending_counts(body)
