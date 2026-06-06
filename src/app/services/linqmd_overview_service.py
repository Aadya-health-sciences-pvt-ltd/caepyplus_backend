"""
LinQMD Overview Generation Service.

Generates patient-facing profile overview text (80-200 words) for LinQMD
profile creation using Gemini, with a deterministic template fallback.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from ..core.config import get_settings
from ..core.prompts import get_prompt_manager
from .gemini_service import get_gemini_service

logger = logging.getLogger(__name__)

_OVERVIEW_MODEL_CONFIG_KEY = "GEMINI_RESUME_MODEL"

MIN_OVERVIEW_WORDS = 80
MAX_OVERVIEW_WORDS = 200


def _word_count(text: str) -> int:
    return len(text.split())


def _trim_to_max_words(text: str, max_words: int = MAX_OVERVIEW_WORDS) -> str:
    """Trim text to max_words, preferring to end at a sentence boundary."""
    words = text.split()
    if len(words) <= max_words:
        return text.strip()

    truncated = " ".join(words[:max_words])
    # Prefer ending at last sentence boundary within truncated text
    for punct in (". ", "! ", "? "):
        idx = truncated.rfind(punct)
        if idx > len(truncated) * 0.5:
            return truncated[: idx + 1].strip()
    return truncated.strip()


def _normalize_overview(text: str) -> str:
    """Clean and enforce word-count bounds on overview text."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    if _word_count(cleaned) > MAX_OVERVIEW_WORDS:
        cleaned = _trim_to_max_words(cleaned, MAX_OVERVIEW_WORDS)
    return cleaned


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _prune_empty(data: dict[str, Any]) -> dict[str, Any]:
    """Remove null/empty keys from a nested dict (one level deep for lists)."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            nested = {k: v for k, v in value.items() if _is_non_empty(v)}
            if nested:
                result[key] = nested
        elif _is_non_empty(value):
            result[key] = value
    return result


def build_doctor_context(
    identity: dict[str, Any],
    details: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build a JSON-serializable context dict for overview generation.

    Omits null/empty fields so the AI works with whatever is available.
    """
    details = details or {}
    context = {
        "identity": {
            "full_name": identity.get("full_name"),
            "email": identity.get("email"),
            "phone_number": identity.get("phone_number"),
        },
        "professional_identity": {
            "specialty": details.get("speciality") or details.get("specialty"),
            "primary_practice_location": details.get("primary_practice_location"),
            "centres_of_practice": details.get("centres_of_practice"),
            "practice_locations": details.get("practice_locations"),
            "years_of_clinical_experience": details.get("years_of_clinical_experience"),
            "years_post_specialisation": details.get("years_post_specialisation"),
            "languages": details.get("languages"),
            "consultation_fee": details.get("consultation_fee"),
            "medical_registration_number": details.get("medical_registration_number"),
            "medical_council": details.get("medical_council"),
        },
        "credentials": {
            "qualifications": details.get("qualifications"),
            "fellowships": details.get("fellowships"),
            "year_of_mbbs": details.get("year_of_mbbs"),
            "year_of_specialisation": details.get("year_of_specialisation"),
            "professional_memberships": details.get("professional_memberships"),
            "awards_academic_honours": details.get("awards_academic_honours"),
        },
        "clinical_focus": {
            "areas_of_clinical_interest": details.get("areas_of_clinical_interest")
            or details.get("areas_of_expertise"),
            "practice_segments": details.get("practice_segments"),
            "conditions_commonly_treated": details.get("conditions_commonly_treated")
            or details.get("conditions_treated"),
            "conditions_known_for": details.get("conditions_known_for"),
            "conditions_want_to_treat_more": details.get("conditions_want_to_treat_more"),
            "procedures_performed": details.get("procedures_performed"),
        },
        "human_side": {
            "training_experience": details.get("training_experience"),
            "motivation_in_practice": details.get("motivation_in_practice"),
            "professional_achievement": details.get("professional_achievement")
            or details.get("professional_overview"),
            "personal_achievement": details.get("personal_achievement")
            or details.get("about_me"),
            "professional_aspiration": details.get("professional_aspiration"),
            "personal_aspiration": details.get("personal_aspiration"),
            "recognition_identity": details.get("recognition_identity"),
            "quality_time_interests": details.get("quality_time_interests"),
            "quality_time_interests_text": details.get("quality_time_interests_text"),
        },
        "patient_value": {
            "what_patients_value_most": details.get("what_patients_value_most"),
            "approach_to_care": details.get("approach_to_care"),
            "availability_philosophy": details.get("availability_philosophy"),
        },
    }
    return _prune_empty(context)


def _join_list(items: list[Any] | None, limit: int = 5) -> str:
    if not items:
        return ""
    parts: list[str] = []
    for item in items[:limit]:
        if isinstance(item, str) and item.strip():
            parts.append(item.strip())
        elif isinstance(item, dict):
            label = item.get("hospital_name") or item.get("name") or item.get("city")
            if label and str(label).strip():
                parts.append(str(label).strip())
    return ", ".join(parts)


def _build_fallback_overview(context: dict[str, Any]) -> str:
    """Deterministic template overview when AI generation fails."""
    identity = context.get("identity", {})
    prof = context.get("professional_identity", {})
    creds = context.get("credentials", {})
    clinical = context.get("clinical_focus", {})
    human = context.get("human_side", {})
    patient = context.get("patient_value", {})

    name = (identity.get("full_name") or "The doctor").strip()
    if not name.lower().startswith("dr"):
        name = f"Dr. {name}"

    specialty = prof.get("specialty") or "medicine"
    location = prof.get("primary_practice_location") or ""
    years = prof.get("years_post_specialisation") or prof.get("years_of_clinical_experience")

    sentences: list[str] = []

    exp_clause = f" with {years} years of clinical experience" if years else ""
    loc_clause = f" based in {location}" if location else ""
    sentences.append(
        f"{name} is a practising {specialty} specialist{exp_clause}{loc_clause}."
    )

    expertise = _join_list(clinical.get("areas_of_clinical_interest"))
    conditions = _join_list(clinical.get("conditions_commonly_treated"))
    if expertise:
        sentences.append(
            f"Renowned for expertise in {expertise}, {name.split()[0]} brings "
            f"focused clinical knowledge to patient care."
        )
    elif conditions:
        sentences.append(
            f"{name} has extensive experience treating conditions including "
            f"{conditions}."
        )

    quals = creds.get("qualifications") or []
    qual_str = _join_list(quals if isinstance(quals, list) else [])
    if qual_str:
        sentences.append(f"Educational qualifications include {qual_str}.")

    langs = _join_list(prof.get("languages"))
    if langs:
        sentences.append(f"Fluent in {langs}, enabling clear communication with diverse patients.")

    approach = patient.get("approach_to_care") or patient.get("what_patients_value_most")
    if approach and isinstance(approach, str):
        sentences.append(
            f"{name.split()[0]} is known for a patient-centred approach to care, "
            f"emphasising {approach.strip().rstrip('.')}."
        )

    achievement = human.get("professional_achievement")
    if achievement and isinstance(achievement, str):
        sentences.append(achievement.strip().rstrip(".") + ".")

    overview = " ".join(sentences)
    overview = _normalize_overview(overview)

    if _word_count(overview) < MIN_OVERVIEW_WORDS:
        sentences.append(
            f"{name.split()[0]} is committed to providing compassionate, evidence-based "
            f"care and building lasting relationships with patients and their families."
        )
        overview = _normalize_overview(" ".join(sentences))

    return overview


class LinqmdOverviewService:
    """Generate patient-facing LinQMD profile overview text."""

    async def generate_overview(self, context: dict[str, Any]) -> str:
        """Call Gemini to generate overview; raises on failure."""
        settings = get_settings()
        prompt_manager = get_prompt_manager()
        prompt = prompt_manager.get_linqmd_overview_prompt(context)
        gemini = get_gemini_service()
        result = await gemini.generate_structured(
            prompt,
            temperature=0.4,
            max_tokens=settings.GEMINI_RESUME_MAX_TOKENS,
            model=settings.GEMINI_RESUME_MODEL,
            config_key=_OVERVIEW_MODEL_CONFIG_KEY,
        )
        overview = result.get("overview", "")
        if not isinstance(overview, str) or not overview.strip():
            raise ValueError("Gemini returned empty overview")
        return _normalize_overview(overview)

    async def generate_with_fallback(
        self,
        identity: dict[str, Any],
        details: dict[str, Any] | None,
    ) -> str:
        """
        Generate overview via AI; fall back to template on any error.

        Never raises — LinQMD profile create must always proceed.
        """
        context = build_doctor_context(identity, details)
        try:
            overview = await self.generate_overview(context)
            if overview:
                logger.info(
                    "LinQMD overview generated via AI words=%d",
                    _word_count(overview),
                )
                return overview
        except Exception as exc:
            logger.warning(
                "LinQMD AI overview generation failed, using fallback: %s",
                exc,
            )
        fallback = _build_fallback_overview(context)
        logger.info(
            "LinQMD overview using template fallback words=%d",
            _word_count(fallback),
        )
        return fallback


_linqmd_overview_service: LinqmdOverviewService | None = None


def get_linqmd_overview_service() -> LinqmdOverviewService:
    """Get the global LinQMD overview service instance."""
    global _linqmd_overview_service
    if _linqmd_overview_service is None:
        _linqmd_overview_service = LinqmdOverviewService()
    return _linqmd_overview_service
