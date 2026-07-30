"""Unit tests for LinQMD specialities_long generation."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.services.linqmd_specialities_long_service import (
    LinqmdSpecialitiesLongService,
    _build_fallback_specialities_long,
    collect_specialities_long_inputs,
)


def test_collect_specialities_long_inputs() -> None:
    inputs = collect_specialities_long_inputs(
        {
            "specialty": "Cardiology",
            "professional_achievement": "Advanced interventional cardiology",
        }
    )
    assert inputs["speciality"] == "Cardiology"
    assert inputs["professional_achievement"] == "Advanced interventional cardiology"


def test_fallback_weaves_speciality_and_achievement() -> None:
    identity = {"full_name": "Dr Anjali Sharma"}
    inputs = {
        "speciality": "Cardiology",
        "professional_achievement": "Advanced interventional and preventive cardiology",
    }
    text = _build_fallback_specialities_long(identity, inputs)
    assert "Cardiology" in text
    assert "interventional" in text
    assert text.endswith(".")


@pytest.mark.asyncio
async def test_generate_with_fallback_uses_gemini() -> None:
    service = LinqmdSpecialitiesLongService()
    identity = {"full_name": "Dr Anjali Sharma"}
    details = {
        "specialty": "Cardiology",
        "professional_achievement": "Advanced interventional cardiology",
    }

    with patch(
        "src.app.services.linqmd_specialities_long_service.get_gemini_service"
    ) as mock_gemini_factory:
        mock_gemini = MagicMock()
        mock_gemini.generate_structured = AsyncMock(
            return_value={
                "specialities_long": (
                    "Dr. Anjali Sharma is a Cardiology specialist with a focus on "
                    "advanced interventional cardiology, helping patients navigate "
                    "heart care with clarity and confidence."
                )
            }
        )
        mock_gemini_factory.return_value = mock_gemini

        text = await service.generate_with_fallback(identity, details)

    assert "Cardiology" in text
    assert text.endswith(".")


@pytest.mark.asyncio
async def test_generate_with_fallback_returns_empty_when_no_inputs() -> None:
    service = LinqmdSpecialitiesLongService()
    text = await service.generate_with_fallback({"full_name": "Dr Test"}, {})
    assert text == ""
