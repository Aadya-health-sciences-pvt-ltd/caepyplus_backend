"""Unit tests for GeminiService Vertex / model resolution."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.app.services.gemini_service import GeminiService


@patch("src.app.services.gemini_service.create_genai_client_with_fallback")
@patch("src.app.services.gemini_service.get_settings")
def test_gemini_service_uses_vertex_client(mock_settings, mock_create):
    settings = MagicMock()
    settings.GEMINI_MODEL = "gemini-2.5-flash"
    settings.GOOGLE_CLOUD_PROJECT = "proj"
    settings.GOOGLE_CLOUD_LOCATION = "us-central1"
    settings.GOOGLE_API_KEY = ""
    mock_settings.return_value = settings
    mock_create.return_value = (MagicMock(), True)

    service = GeminiService()
    _ = service.client

    mock_create.assert_called_once_with(settings)
    assert service._use_vertex is True


@patch("src.app.services.gemini_service.create_genai_client_with_fallback")
@patch("src.app.services.gemini_service.get_settings")
def test_resolve_model_strips_prefix_for_vertex(mock_settings, mock_create):
    settings = MagicMock()
    settings.GEMINI_MODEL = "gemini-2.5-flash"
    settings.GOOGLE_CLOUD_PROJECT = "proj"
    settings.GOOGLE_CLOUD_LOCATION = "us-central1"
    mock_settings.return_value = settings
    mock_create.return_value = (MagicMock(), True)

    service = GeminiService()
    _ = service.client

    assert service._resolve_model("gemini-2.5-flash") == "gemini-2.5-flash"
    assert service._resolve_model("models/gemini-2.5-flash") == "gemini-2.5-flash"


@patch("src.app.services.gemini_service.create_genai_client_with_fallback")
@patch("src.app.services.gemini_service.get_settings")
def test_resolve_model_adds_prefix_for_ai_studio(mock_settings, mock_create):
    settings = MagicMock()
    settings.GEMINI_MODEL = "gemini-2.5-flash"
    settings.GOOGLE_API_KEY = "key"
    mock_settings.return_value = settings
    mock_create.return_value = (MagicMock(), False)

    service = GeminiService()
    _ = service.client

    assert service._resolve_model("gemini-2.5-flash") == "models/gemini-2.5-flash"
