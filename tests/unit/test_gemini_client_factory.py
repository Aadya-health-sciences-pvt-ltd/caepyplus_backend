"""Unit tests for shared Gemini Vertex / AI Studio client factory."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.app.core.exceptions import AIServiceError
from src.app.services.gemini_client_factory import (
    create_genai_client,
    normalize_model_id,
    should_use_vertex,
)


def _settings(
    *,
    creds: str = "",
    api_key: str = "",
    project: str = "test-project",
    location: str = "us-central1",
) -> MagicMock:
    s = MagicMock()
    s.GOOGLE_APPLICATION_CREDENTIALS = creds
    s.GOOGLE_API_KEY = api_key
    s.GOOGLE_CLOUD_PROJECT = project
    s.GOOGLE_CLOUD_LOCATION = location
    return s


class TestShouldUseVertex:
    def test_vertex_when_credentials_file_exists(self, tmp_path):
        cred_file = tmp_path / "sa.json"
        cred_file.write_text("{}")
        settings = _settings(creds=str(cred_file), api_key="key")
        assert should_use_vertex(settings, "gemini-2.5-flash") is True

    def test_ai_studio_when_no_credentials(self):
        settings = _settings(api_key="key")
        assert should_use_vertex(settings, "gemini-2.5-flash") is False

    def test_ai_studio_fallback_for_gemini_3_1_with_api_key(self, tmp_path):
        cred_file = tmp_path / "sa.json"
        cred_file.write_text("{}")
        settings = _settings(creds=str(cred_file), api_key="key")
        assert (
            should_use_vertex(settings, "gemini-3.1-flash-live-preview") is False
        )


class TestNormalizeModelId:
    def test_vertex_strips_models_prefix(self):
        assert normalize_model_id("models/gemini-2.5-flash", use_vertex=True) == (
            "gemini-2.5-flash"
        )

    def test_ai_studio_adds_models_prefix(self):
        assert normalize_model_id("gemini-2.5-flash", use_vertex=False) == (
            "models/gemini-2.5-flash"
        )


class TestCreateGenaiClient:
    def test_raises_when_ai_studio_without_api_key(self):
        settings = _settings()
        with pytest.raises(AIServiceError):
            create_genai_client(settings, use_vertex=False)

    @patch("src.app.services.gemini_client_factory.genai.Client")
    def test_creates_vertex_client(self, mock_client_cls):
        settings = _settings()
        create_genai_client(settings, use_vertex=True)
        mock_client_cls.assert_called_once_with(
            vertexai=True,
            project="test-project",
            location="us-central1",
            http_options={"api_version": "v1beta1"},
        )

    @patch("src.app.services.gemini_client_factory.genai.Client")
    def test_creates_ai_studio_client(self, mock_client_cls):
        settings = _settings(api_key="test-key")
        create_genai_client(settings, use_vertex=False)
        mock_client_cls.assert_called_once_with(api_key="test-key")
