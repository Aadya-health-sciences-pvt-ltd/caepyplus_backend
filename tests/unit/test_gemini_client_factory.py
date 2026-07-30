"""Unit tests for shared Gemini Vertex / AI Studio client factory."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.app.core.exceptions import AIServiceError
from src.app.services.gemini_client_factory import (
    create_genai_client,
    create_genai_client_with_fallback,
    normalize_model_id,
    should_use_vertex,
)

_FAKE_SA = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "abc",
    "private_key": "-----BEGIN PRIVATE KEY-----\\nFAKE\\n-----END PRIVATE KEY-----\\n",
    "client_email": "test@test.iam.gserviceaccount.com",
}


def _settings(
    *,
    sa_json: str = "",
    api_key: str = "",
    project: str = "test-project",
    location: str = "us-central1",
) -> MagicMock:
    s = MagicMock()
    s.GCP_SERVICE_ACCOUNT_JSON = sa_json
    s.GOOGLE_API_KEY = api_key
    s.GOOGLE_CLOUD_PROJECT = project
    s.GOOGLE_CLOUD_LOCATION = location
    s.has_vertex_credentials.return_value = bool(sa_json)
    s.resolved_vertex_project.return_value = project
    return s


class TestShouldUseVertex:
    def test_vertex_when_inline_json_configured(self):
        settings = _settings(sa_json=json.dumps(_FAKE_SA), api_key="key")
        assert should_use_vertex(settings, "gemini-2.5-flash") is True

    def test_ai_studio_when_no_credentials(self):
        settings = _settings(api_key="key")
        assert should_use_vertex(settings, "gemini-2.5-flash") is False


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

    @patch("src.app.services.gemini_client_factory.build_vertex_credentials")
    @patch("src.app.services.gemini_client_factory.genai.Client")
    def test_creates_vertex_client_with_credentials(
        self, mock_client_cls, mock_build_creds
    ):
        mock_creds = MagicMock()
        mock_build_creds.return_value = mock_creds
        settings = _settings(sa_json=json.dumps(_FAKE_SA))

        create_genai_client(settings, use_vertex=True)

        mock_build_creds.assert_called_once_with(settings)
        mock_client_cls.assert_called_once_with(
            vertexai=True,
            project="test-project",
            location="us-central1",
            credentials=mock_creds,
        )

    @patch("src.app.services.gemini_client_factory.genai.Client")
    def test_creates_ai_studio_client(self, mock_client_cls):
        settings = _settings(api_key="test-key")
        create_genai_client(settings, use_vertex=False)
        mock_client_cls.assert_called_once_with(api_key="test-key")


class TestCreateGenaiClientWithFallback:
    @patch("src.app.services.gemini_client_factory.create_genai_client")
    @patch("src.app.services.gemini_client_factory.verify_vertex_connection")
    def test_uses_vertex_when_connection_succeeds(
        self, mock_verify, mock_create_client
    ):
        settings = _settings(sa_json=json.dumps(_FAKE_SA), api_key="key")
        vertex_client = MagicMock()
        mock_create_client.return_value = vertex_client

        client, use_vertex = create_genai_client_with_fallback(settings)

        mock_verify.assert_called_once_with(settings)
        mock_create_client.assert_called_once_with(settings, use_vertex=True)
        assert client is vertex_client
        assert use_vertex is True

    @patch("src.app.services.gemini_client_factory.create_genai_client")
    @patch("src.app.services.gemini_client_factory.verify_vertex_connection")
    def test_falls_back_to_ai_studio_when_vertex_fails(
        self, mock_verify, mock_create_client
    ):
        mock_verify.side_effect = AIServiceError(message="bad creds", original_error="x")
        settings = _settings(sa_json=json.dumps(_FAKE_SA), api_key="key")
        ai_client = MagicMock()
        mock_create_client.return_value = ai_client

        client, use_vertex = create_genai_client_with_fallback(settings)

        mock_create_client.assert_called_once_with(settings, use_vertex=False)
        assert client is ai_client
        assert use_vertex is False

    @patch("src.app.services.gemini_client_factory.create_genai_client")
    @patch("src.app.services.gemini_client_factory.verify_vertex_connection")
    def test_skips_vertex_when_json_not_configured(
        self, mock_verify, mock_create_client
    ):
        settings = _settings(api_key="key")
        ai_client = MagicMock()
        mock_create_client.return_value = ai_client

        client, use_vertex = create_genai_client_with_fallback(settings)

        mock_verify.assert_not_called()
        mock_create_client.assert_called_once_with(settings, use_vertex=False)
        assert client is ai_client
        assert use_vertex is False
