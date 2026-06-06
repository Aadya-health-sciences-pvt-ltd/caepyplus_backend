"""Unit tests for LinQMD overview generation service."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.app.services.linqmd_overview_service import (
    LinqmdOverviewService,
    _build_fallback_overview,
    _normalize_overview,
    _trim_to_max_words,
    _word_count,
    build_doctor_context,
)


class TestWordCountHelpers:
    def test_word_count(self):
        assert _word_count("one two three") == 3

    def test_trim_to_max_words_at_sentence_boundary(self):
        text = (
            "Dr. Smith is a cardiologist with extensive experience. "
            "He treats many conditions. He cares deeply for patients. "
            "He speaks multiple languages fluently."
        )
        trimmed = _trim_to_max_words(text, max_words=15)
        assert _word_count(trimmed) <= 15
        assert trimmed.endswith(".")

    def test_normalize_overview_trims_long_text(self):
        words = ["word"] * 250
        long_text = " ".join(words)
        result = _normalize_overview(long_text)
        assert _word_count(result) <= 200


class TestBuildDoctorContext:
    def test_omits_empty_fields(self):
        context = build_doctor_context(
            {"full_name": "Dr. Anjali Sharma", "email": "a@example.com"},
            {"speciality": "Cardiology"},
        )
        assert "identity" in context
        assert context["identity"]["full_name"] == "Dr. Anjali Sharma"
        assert context["professional_identity"]["specialty"] == "Cardiology"
        assert "credentials" not in context or not context.get("credentials")

    def test_includes_rich_onboarding_fields(self):
        context = build_doctor_context(
            {"full_name": "Dr. Test"},
            {
                "speciality": "Pediatrics",
                "years_of_clinical_experience": 17,
                "languages": ["English", "Hindi"],
                "areas_of_clinical_interest": ["Allergy", "Asthma"],
                "approach_to_care": "Holistic family-centred care",
            },
        )
        assert context["professional_identity"]["languages"] == ["English", "Hindi"]
        assert context["clinical_focus"]["areas_of_clinical_interest"] == [
            "Allergy",
            "Asthma",
        ]
        assert context["patient_value"]["approach_to_care"] == "Holistic family-centred care"


class TestFallbackOverview:
    def test_minimal_data_produces_text(self):
        context = build_doctor_context(
            {"full_name": "Balachandra"},
            {"speciality": "Pediatrics", "years_of_clinical_experience": 17},
        )
        overview = _build_fallback_overview(context)
        assert "Dr." in overview
        assert "Pediatrics" in overview
        assert _word_count(overview) >= 1

    def test_rich_data_mentions_expertise(self):
        context = build_doctor_context(
            {"full_name": "Dr. Deepa Chandran"},
            {
                "speciality": "Neuroanaesthesiology",
                "primary_practice_location": "Bangalore",
                "years_post_specialisation": 19,
                "areas_of_clinical_interest": ["Neurosurgical anaesthesia"],
                "languages": ["English"],
            },
        )
        overview = _build_fallback_overview(context)
        assert "Deepa" in overview or "Dr." in overview
        assert "Bangalore" in overview or "Neuroanaesthesiology" in overview


class TestLinqmdOverviewService:
    @pytest.mark.asyncio
    async def test_generate_overview_parses_ai_response(self):
        service = LinqmdOverviewService()
        long_overview = " ".join(["patient"] * 100)

        with patch(
            "src.app.services.linqmd_overview_service.get_gemini_service"
        ) as mock_gemini_cls:
            mock_gemini = AsyncMock()
            mock_gemini.generate_structured = AsyncMock(
                return_value={"overview": long_overview}
            )
            mock_gemini_cls.return_value = mock_gemini

            result = await service.generate_overview({"identity": {"full_name": "Dr. X"}})

        assert _word_count(result) <= 200
        call_kwargs = mock_gemini.generate_structured.await_args.kwargs
        assert call_kwargs["config_key"] == "GEMINI_RESUME_MODEL"
        assert "model" in call_kwargs

    @pytest.mark.asyncio
    async def test_generate_with_fallback_uses_ai_on_success(self):
        service = LinqmdOverviewService()
        ai_text = " ".join(["care"] * 90)

        with patch.object(
            service, "generate_overview", new=AsyncMock(return_value=ai_text)
        ):
            result = await service.generate_with_fallback(
                {"full_name": "Dr. Test"},
                {"speciality": "Cardiology"},
            )

        assert result == ai_text

    @pytest.mark.asyncio
    async def test_generate_with_fallback_never_raises(self):
        service = LinqmdOverviewService()

        with patch.object(
            service,
            "generate_overview",
            new=AsyncMock(side_effect=RuntimeError("API down")),
        ):
            result = await service.generate_with_fallback(
                {"full_name": "Dr. Test"},
                {"speciality": "Cardiology", "years_of_clinical_experience": 10},
            )

        assert isinstance(result, str)
        assert len(result) > 0
