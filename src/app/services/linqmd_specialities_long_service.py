"""
LinQMD specialities_long generation.

Transforms speciality + professional_achievement into patient-friendly prose for
LinQMD profile create/update using Gemini, with a deterministic fallback.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from ..core.config import get_settings
from ..core.prompts import get_prompt_manager
from .gemini_service import get_gemini_service

logger = logging.getLogger(__name__)

_MODEL_CONFIG_KEY = "GEMINI_RESUME_MODEL"
_MAX_WORDS = 100


def _word_count(text: str) -> int:
    return len(text.split())


def _resolve_speciality(details: dict[str, Any]) -> str:
    value = details.get("speciality") or details.get("specialty") or ""
    return str(value).strip() if value else ""


def _resolve_professional_achievement(details: dict[str, Any]) -> str:
    value = details.get("professional_achievement") or ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip() if value else ""


def collect_specialities_long_inputs(
    details: dict[str, Any] | None,
) -> dict[str, str]:
    details = details or {}
    return {
        "speciality": _resolve_speciality(details),
        "professional_achievement": _resolve_professional_achievement(details),
    }


def _has_specialities_long_inputs(inputs: dict[str, str]) -> bool:
    return bool(inputs.get("speciality") or inputs.get("professional_achievement"))


def _normalize_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    if not cleaned.endswith("."):
        cleaned += "."
    words = cleaned.split()
    if len(words) > _MAX_WORDS:
        truncated = " ".join(words[:_MAX_WORDS])
        for punct in (". ", "! ", "? "):
            idx = truncated.rfind(punct)
            if idx > len(truncated) * 0.5:
                return truncated[: idx + 1].strip()
        return truncated.rstrip(",;") + "."
    return cleaned


def _build_fallback_specialities_long(
    identity: dict[str, Any],
    inputs: dict[str, str],
) -> str:
    """Patient-friendly paragraph when Gemini is unavailable."""
    if not _has_specialities_long_inputs(inputs):
        return ""

    name = (identity.get("full_name") or "").strip()
    if name and not name.lower().startswith("dr"):
        name = f"Dr. {name}"

    speciality = inputs.get("speciality", "")
    achievement = inputs.get("professional_achievement", "")

    if speciality and achievement:
        if name:
            text = (
                f"As a {speciality} specialist, {name} brings a focus on "
                f"{achievement.rstrip('.')}, helping patients understand their "
                f"care with clarity and confidence."
            )
        else:
            text = (
                f"This {speciality} practice specialises in {achievement.rstrip('.')}, "
                f"with care explained in clear, patient-friendly language."
            )
    elif speciality:
        if name:
            text = (
                f"{name} is a {speciality} specialist dedicated to providing "
                f"compassionate, evidence-based care tailored to each patient."
            )
        else:
            text = (
                f"A {speciality} specialist focused on accessible, patient-centred care."
            )
    else:
        if name:
            text = (
                f"{name} focuses on {achievement.rstrip('.')}, with an emphasis on "
                f"clear communication and trusted clinical care."
            )
        else:
            text = achievement.rstrip(".") + "."

    return _normalize_text(text)


class LinqmdSpecialitiesLongService:
    """Generate LinQMD specialities_long text."""

    async def generate_specialities_long(
        self,
        identity: dict[str, Any],
        inputs: dict[str, str],
    ) -> str:
        settings = get_settings()
        prompt_manager = get_prompt_manager()
        context = {
            "doctor_name": identity.get("full_name"),
            **inputs,
        }
        prompt = prompt_manager.get_linqmd_specialities_long_prompt(context)
        gemini = get_gemini_service()
        result = await gemini.generate_structured(
            prompt,
            temperature=0.35,
            max_tokens=settings.GEMINI_RESUME_MAX_TOKENS,
            model=settings.GEMINI_RESUME_MODEL,
            config_key=_MODEL_CONFIG_KEY,
        )
        text = result.get("specialities_long", "")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Gemini returned empty specialities_long")
        return _normalize_text(text)

    async def generate_with_fallback(
        self,
        identity: dict[str, Any],
        details: dict[str, Any] | None,
    ) -> str:
        """Generate via AI; fall back to template. Never raises."""
        inputs = collect_specialities_long_inputs(details)
        if not _has_specialities_long_inputs(inputs):
            return ""

        try:
            text = await self.generate_specialities_long(identity, inputs)
            if text:
                logger.info(
                    "LinQMD specialities_long generated via AI words=%d",
                    _word_count(text),
                )
                return text
        except Exception as exc:
            logger.warning(
                "LinQMD AI specialities_long generation failed, using fallback: %s",
                exc,
            )

        fallback = _build_fallback_specialities_long(identity, inputs)
        if fallback:
            logger.info(
                "LinQMD specialities_long using template fallback words=%d",
                _word_count(fallback),
            )
        return fallback


_linqmd_specialities_long_service: LinqmdSpecialitiesLongService | None = None


def get_linqmd_specialities_long_service() -> LinqmdSpecialitiesLongService:
    global _linqmd_specialities_long_service
    if _linqmd_specialities_long_service is None:
        _linqmd_specialities_long_service = LinqmdSpecialitiesLongService()
    return _linqmd_specialities_long_service
