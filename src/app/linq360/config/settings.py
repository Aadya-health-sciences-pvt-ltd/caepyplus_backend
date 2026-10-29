"""Linq360 module settings helpers (pydantic-friendly parsing)."""
from __future__ import annotations

from ...core.config import get_settings
from ..common.open_domains import parse_open_domains


def ai_suggestions_open_domains() -> list[str]:
    """Trusted origins for dashboard webhook domain auth (from env)."""
    return parse_open_domains(get_settings().AI_SUGGESTIONS_OPEN_DOMAINS)
