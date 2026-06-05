"""Unit tests for Gemini logging helpers."""
from __future__ import annotations

from src.app.services.gemini_service import gemini_remediation_hint, mask_api_key


def test_mask_api_key_shows_fingerprint() -> None:
    assert mask_api_key("AIzaSyAbCdEfGhIjKlMn") == "AIza...KlMn"


def test_mask_api_key_empty() -> None:
    assert mask_api_key("") == "<not set>"


def test_remediation_for_live_model_not_found() -> None:
    hint = gemini_remediation_hint(
        "404 NOT_FOUND models/gemini-3.1-flash-live-preview is not supported for generateContent",
        "gemini-3.1-flash-live-preview",
    )
    assert "gemini-2.5-flash" in hint
    assert "Live" in hint or "live" in hint


def test_remediation_for_quota_exhausted() -> None:
    hint = gemini_remediation_hint(
        "429 RESOURCE_EXHAUSTED prepayment credits are depleted",
        "gemini-2.5-flash",
    )
    assert "quota" in hint.lower() or "billing" in hint.lower()
