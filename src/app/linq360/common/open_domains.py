"""Open-domain allowlist helpers (ported from Nest AiSuggestionsDomainAuthMiddleware)."""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse


def parse_open_domains(raw: str | None) -> list[str]:
    """Parse ``AI_SUGGESTIONS_OPEN_DOMAINS`` as JSON array or comma-separated list."""
    trimmed = (raw or "").strip()
    if not trimmed:
        return []

    if trimmed.startswith("["):
        try:
            parsed = json.loads(trimmed)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item).strip() for item in parsed if str(item).strip()]

    return [item.strip() for item in trimmed.split(",") if item.strip()]


def origins_match(candidate: str, entry: str) -> bool:
    """True when Origin/Referer candidate matches an allowlist entry."""
    try:
        request_url = urlparse(candidate)
    except ValueError:
        return False
    if not request_url.scheme or not request_url.netloc:
        return False

    request_origin = f"{request_url.scheme}://{request_url.netloc}".lower()
    request_host = request_url.netloc.lower()
    request_hostname = (request_url.hostname or "").lower()

    if re.match(r"^https?://", entry, flags=re.IGNORECASE):
        try:
            entry_url = urlparse(entry)
        except ValueError:
            return False
        if not entry_url.scheme or not entry_url.netloc:
            return False
        entry_origin = f"{entry_url.scheme}://{entry_url.netloc}".lower()
        return entry_origin == request_origin

    host = entry.rstrip("/").lower()
    return host == request_host or host == request_hostname


def request_matches_open_domain(
    origin: str | None,
    referer: str | None,
    allowlist: list[str],
) -> bool:
    """True when Origin or Referer matches any allowlist entry."""
    if not allowlist:
        return False

    candidates = [
        value
        for value in (origin, referer)
        if isinstance(value, str) and value.strip()
    ]
    return any(
        origins_match(candidate, entry)
        for candidate in candidates
        for entry in allowlist
    )
