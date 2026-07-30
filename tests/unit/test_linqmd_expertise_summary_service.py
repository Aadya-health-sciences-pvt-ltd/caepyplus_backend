"""Unit tests for LinQMD expertise_summary generation."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.app.services.linqmd_expertise_summary_service import (
    LinqmdExpertiseSummaryService,
    _build_fallback_expertise_summary,
    collect_expertise_inputs,
)


def test_collect_expertise_inputs_merges_aliases() -> None:
    inputs = collect_expertise_inputs(
        {
            "conditions_commonly_treated": ["Hypertension"],
            "areas_of_clinical_interest": ["Interventional Cardiology"],
            "procedures_performed": ["Angioplasty"],
        }
    )
    assert inputs["conditions_commonly_treated"] == ["Hypertension"]
    assert inputs["areas_of_expertise"] == ["Interventional Cardiology"]
    assert inputs["procedures_performed"] == ["Angioplasty"]


def test_collect_expertise_inputs_ignores_empty() -> None:
    assert collect_expertise_inputs({}) == {
        "conditions_commonly_treated": [],
        "areas_of_expertise": [],
        "procedures_performed": [],
    }


def test_fallback_builds_professional_sentence() -> None:
    identity = {"full_name": "Dr Anjali Sharma"}
    inputs = {
        "conditions_commonly_treated": ["Hypertension", "Heart Failure"],
        "areas_of_expertise": ["Interventional Cardiology"],
        "procedures_performed": ["Angioplasty"],
    }
    summary = _build_fallback_expertise_summary(identity, inputs)
    assert summary.endswith(".")
    assert "Hypertension" in summary
    assert "Interventional Cardiology" in summary
    assert "Angioplasty" in summary


@pytest.mark.asyncio
async def test_generate_with_fallback_uses_gemini() -> None:
    service = LinqmdExpertiseSummaryService()
    identity = {"full_name": "Dr Test"}
    details = {
        "specialty": "Cardiology",
        "conditions_commonly_treated": ["Hypertension"],
        "areas_of_clinical_interest": ["Preventive cardiology"],
    }

    with patch(
        "src.app.services.linqmd_expertise_summary_service.get_gemini_service"
    ) as mock_gemini_factory:
        mock_gemini = MagicMock()
        mock_gemini.generate_structured = AsyncMock(
            return_value={
                "expertise_summary": (
                    "Dr. Test specialises in preventive cardiology with "
                    "extensive experience managing hypertension."
                )
            }
        )
        mock_gemini_factory.return_value = mock_gemini

        summary = await service.generate_with_fallback(identity, details)

    assert "preventive cardiology" in summary
    assert summary.endswith(".")


@pytest.mark.asyncio
async def test_generate_with_fallback_returns_empty_when_no_inputs() -> None:
    service = LinqmdExpertiseSummaryService()
    summary = await service.generate_with_fallback({"full_name": "Dr Test"}, {})
    assert summary == ""
