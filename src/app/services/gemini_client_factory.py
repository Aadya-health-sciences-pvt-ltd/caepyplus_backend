"""
Shared Gemini client factory — Vertex AI vs Google AI Studio.

Used by voice (Live API) and generateContent flows (resume extraction, etc.)
so backend selection stays identical across services.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from google import genai

from ..core.exceptions import AIServiceError

if TYPE_CHECKING:
    from ..core.config import Settings


def should_use_vertex(settings: Settings, model_id: str) -> bool:
    """
    Decide whether to use Vertex AI or Google AI Studio.

    Matches voice onboarding logic:
    - Vertex when GOOGLE_APPLICATION_CREDENTIALS file exists
    - Fall back to AI Studio when model is gemini-3.1* and GOOGLE_API_KEY is set
    """
    use_vertex = False
    cred_path = getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", None) or ""
    if cred_path and os.path.exists(cred_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
        use_vertex = True

    # Vertex AI doesn't support gemini-3.1 yet, so fallback to AI Studio if that model is requested
    if model_id and "gemini-3.1" in model_id and getattr(settings, "GOOGLE_API_KEY", None):
        use_vertex = False

    return use_vertex


def create_genai_client(settings: Settings, *, use_vertex: bool) -> genai.Client:
    """Create a google-genai Client for Vertex or AI Studio."""
    if use_vertex:
        return genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
            http_options={"api_version": "v1beta1"},
        )

    api_key = (settings.GOOGLE_API_KEY or "").strip()
    if not api_key:
        raise AIServiceError(
            message="Google API key not configured",
            original_error="GOOGLE_API_KEY environment variable is empty",
        )
    return genai.Client(api_key=api_key)


def normalize_model_id(model_id: str, *, use_vertex: bool) -> str:
    """Apply Vertex vs AI Studio model ID formatting."""
    if use_vertex:
        if model_id.startswith("models/"):
            return model_id.replace("models/", "", 1)
        return model_id

    if not model_id.startswith("models/"):
        return f"models/{model_id}"
    return model_id
