"""
Shared Gemini client factory — Vertex AI vs Google AI Studio.

Used by voice (Live API) and generateContent flows (resume extraction, etc.)
so backend selection stays identical across services.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from google import genai

from ..core.exceptions import AIServiceError
from .gcp_credentials import build_vertex_credentials, verify_vertex_connection

if TYPE_CHECKING:
    from ..core.config import Settings

logger = logging.getLogger(__name__)


def should_use_vertex(settings: Settings, model_id: str = "") -> bool:
    """True when GCP_SERVICE_ACCOUNT_JSON is configured (Vertex will be attempted)."""
    return settings.has_vertex_credentials()


def create_genai_client(settings: Settings, *, use_vertex: bool) -> genai.Client:
    """Create a google-genai Client for Vertex or AI Studio."""
    if use_vertex:
        credentials = build_vertex_credentials(settings)
        project = settings.resolved_vertex_project()
        return genai.Client(
            vertexai=True,
            project=project,
            location=settings.GOOGLE_CLOUD_LOCATION,
            credentials=credentials,
            http_options={"api_version": "v1beta1"},
        )

    api_key = (settings.GOOGLE_API_KEY or "").strip()
    if not api_key:
        raise AIServiceError(
            message="Google API key not configured",
            original_error="GOOGLE_API_KEY environment variable is empty",
        )
    return genai.Client(api_key=api_key)


def create_genai_client_with_fallback(settings: Settings) -> tuple[genai.Client, bool]:
    """
    Create a Gemini client, preferring Vertex when GCP_SERVICE_ACCOUNT_JSON is set.

    Attempts to authenticate with Vertex first. On failure, falls back to AI Studio
    when GOOGLE_API_KEY is configured.
    """
    if settings.has_vertex_credentials():
        try:
            verify_vertex_connection(settings)
            return create_genai_client(settings, use_vertex=True), True
        except Exception as exc:
            logger.warning(
                "Vertex AI connection failed (%s); falling back to Google AI Studio",
                exc,
            )

    return create_genai_client(settings, use_vertex=False), False


def normalize_model_id(model_id: str, *, use_vertex: bool) -> str:
    """Apply Vertex vs AI Studio model ID formatting."""
    if use_vertex:
        if model_id.startswith("models/"):
            return model_id.replace("models/", "", 1)
        return model_id

    if not model_id.startswith("models/"):
        return f"models/{model_id}"
    return model_id
