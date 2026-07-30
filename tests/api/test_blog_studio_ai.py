"""Blog Studio AI model selection."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.app.api.v1.endpoints.blogs import _blog_studio_generate_structured
from src.app.core.config import Settings


@pytest.mark.asyncio
async def test_blog_studio_uses_gemini_resume_model() -> None:
    gemini = MagicMock()
    gemini.generate_structured = AsyncMock(return_value={"topics": []})
    settings = Settings(
        GEMINI_MODEL="gemini-2.5-flash-lite",
        GEMINI_RESUME_MODEL="gemini-2.5-pro",
    )

    await _blog_studio_generate_structured(
        gemini, "prompt", max_tokens=1024, settings=settings
    )

    gemini.generate_structured.assert_awaited_once_with(
        "prompt",
        max_tokens=1024,
        model="gemini-2.5-pro",
        config_key="GEMINI_RESUME_MODEL",
    )
