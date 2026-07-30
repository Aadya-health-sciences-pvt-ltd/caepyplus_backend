"""
LinQMD expertise summary generation.

Builds a professional expertise_summary sentence for LinQMD profile create/update
from conditions commonly treated, areas of expertise, and procedures — using Gemini
with a deterministic fallback.
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
_MAX_SUMMARY_WORDS = 80


def _word_count(text: str) -> int:
    return len(text.split())


def _normalize_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def collect_expertise_inputs(details: dict[str, Any] | None) -> dict[str, list[str]]:
    """Non-empty clinical expertise inputs for LinQMD expertise_summary."""
    details = details or {}
    return {
        "conditions_commonly_treated": _normalize_list(
            details.get("conditions_commonly_treated")
            or details.get("conditions_treated")
        ),
        "areas_of_expertise": _normalize_list(
            details.get("areas_of_clinical_interest")
            or details.get("areas_of_expertise")
        ),
        "procedures_performed": _normalize_list(details.get("procedures_performed")),
    }


def _has_expertise_inputs(inputs: dict[str, list[str]]) -> bool:
    return any(inputs.get(key) for key in inputs)


def _join_natural(items: list[str], *, limit: int = 8) -> str:
    parts = items[:limit]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _normalize_summary(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    if not cleaned.endswith("."):
        cleaned += "."
    words = cleaned.split()
    if len(words) > _MAX_SUMMARY_WORDS:
        truncated = " ".join(words[:_MAX_SUMMARY_WORDS])
        for punct in (". ", "! ", "? "):
            idx = truncated.rfind(punct)
            if idx > len(truncated) * 0.5:
                return truncated[: idx + 1].strip()
        return truncated.rstrip(",;") + "."
    return cleaned


def _build_fallback_expertise_summary(
    identity: dict[str, Any],
    inputs: dict[str, list[str]],
) -> str:
    """Deterministic one-paragraph summary when Gemini is unavailable."""
    if not _has_expertise_inputs(inputs):
        return ""

    name = (identity.get("full_name") or "The doctor").strip()
    if name and not name.lower().startswith("dr"):
        name = f"Dr. {name}"

    conditions = _join_natural(inputs.get("conditions_commonly_treated", []))
    areas = _join_natural(inputs.get("areas_of_expertise", []))
    procedures = _join_natural(inputs.get("procedures_performed", []))

    clauses: list[str] = []
    if conditions:
        clauses.append(f"extensive experience in managing {conditions}")
    if areas:
        clauses.append(f"focused expertise in {areas}")
    if procedures:
        clauses.append(f"skilled in performing {procedures}")

    if not clauses:
        return ""

    if len(clauses) == 1:
        body = clauses[0]
    elif len(clauses) == 2:
        body = f"{clauses[0]} and {clauses[1]}"
    else:
        body = f"{clauses[0]}, {clauses[1]}, and {clauses[2]}"

    return _normalize_summary(f"{name} brings {body} to patient care.")


class LinqmdExpertiseSummaryService:
    """Generate LinQMD expertise_summary text."""

    async def generate_expertise_summary(
        self,
        identity: dict[str, Any],
        details: dict[str, Any] | None,
        inputs: dict[str, list[str]],
    ) -> str:
        settings = get_settings()
        prompt_manager = get_prompt_manager()
        details = details or {}
        context = {
            "doctor_name": identity.get("full_name"),
            "specialty": details.get("speciality") or details.get("specialty"),
            **inputs,
        }
        prompt = prompt_manager.get_linqmd_expertise_summary_prompt(context)
        gemini = get_gemini_service()
        result = await gemini.generate_structured(
            prompt,
            temperature=0.3,
            max_tokens=settings.GEMINI_RESUME_MAX_TOKENS,
            model=settings.GEMINI_RESUME_MODEL,
            config_key=_MODEL_CONFIG_KEY,
        )
        summary = result.get("expertise_summary", "")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Gemini returned empty expertise_summary")
        return _normalize_summary(summary)

    async def generate_with_fallback(
        self,
        identity: dict[str, Any],
        details: dict[str, Any] | None,
    ) -> str:
        """Generate via AI; fall back to template. Never raises."""
        inputs = collect_expertise_inputs(details)
        if not _has_expertise_inputs(inputs):
            return ""

        try:
            summary = await self.generate_expertise_summary(identity, details, inputs)
            if summary:
                logger.info(
                    "LinQMD expertise_summary generated via AI words=%d",
                    _word_count(summary),
                )
                return summary
        except Exception as exc:
            logger.warning(
                "LinQMD AI expertise_summary generation failed, using fallback: %s",
                exc,
            )

        fallback = _build_fallback_expertise_summary(identity, inputs)
        if fallback:
            logger.info(
                "LinQMD expertise_summary using template fallback words=%d",
                _word_count(fallback),
            )
        return fallback


_linqmd_expertise_summary_service: LinqmdExpertiseSummaryService | None = None


def get_linqmd_expertise_summary_service() -> LinqmdExpertiseSummaryService:
    global _linqmd_expertise_summary_service
    if _linqmd_expertise_summary_service is None:
        _linqmd_expertise_summary_service = LinqmdExpertiseSummaryService()
    return _linqmd_expertise_summary_service
