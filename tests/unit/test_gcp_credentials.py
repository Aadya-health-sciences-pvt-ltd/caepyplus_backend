"""Unit tests for GCP service account settings and credential builder."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.app.core.config import get_settings
from src.app.core.exceptions import AIServiceError
from src.app.services.gcp_credentials import (
    build_vertex_credentials,
    normalize_service_account_info,
    verify_vertex_connection,
    vertex_auth_label,
)

_FAKE_SA = {
    "type": "service_account",
    "project_id": "linqmd-stg",
    "private_key_id": "abc123",
    "private_key": "-----BEGIN PRIVATE KEY-----\\nFAKE\\n-----END PRIVATE KEY-----\\n",
    "client_email": "prod-caepy-api@linqmd-stg.iam.gserviceaccount.com",
    "client_id": "117585752351628625391",
    "token_uri": "https://oauth2.googleapis.com/token",
}


class TestSettingsGcpServiceAccount:
    def test_parsed_gcp_service_account_valid(self, monkeypatch):
        monkeypatch.setenv("GCP_SERVICE_ACCOUNT_JSON", json.dumps(_FAKE_SA))
        get_settings.cache_clear()
        settings = get_settings()
        parsed = settings.parsed_gcp_service_account()
        assert parsed is not None
        assert parsed["client_email"] == _FAKE_SA["client_email"]
        get_settings.cache_clear()

    def test_parsed_gcp_service_account_invalid_json(self, monkeypatch):
        monkeypatch.setenv("GCP_SERVICE_ACCOUNT_JSON", "not-json")
        get_settings.cache_clear()
        settings = get_settings()
        assert settings.parsed_gcp_service_account() is None
        get_settings.cache_clear()

    def test_has_vertex_credentials_from_json(self, monkeypatch):
        monkeypatch.setenv("GCP_SERVICE_ACCOUNT_JSON", json.dumps(_FAKE_SA))
        get_settings.cache_clear()
        assert get_settings().has_vertex_credentials() is True
        get_settings.cache_clear()

    def test_has_vertex_credentials_false_without_json(self, monkeypatch):
        monkeypatch.setenv("GCP_SERVICE_ACCOUNT_JSON", "")
        get_settings.cache_clear()
        assert get_settings().has_vertex_credentials() is False
        get_settings.cache_clear()

    def test_resolved_vertex_project_prefers_env(self, monkeypatch):
        monkeypatch.setenv("GCP_SERVICE_ACCOUNT_JSON", json.dumps(_FAKE_SA))
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "explicit-project")
        get_settings.cache_clear()
        assert get_settings().resolved_vertex_project() == "explicit-project"
        get_settings.cache_clear()


class TestNormalizeServiceAccountInfo:
    def test_replaces_escaped_newlines_in_private_key(self):
        info = {"private_key": "line1\\nline2"}
        assert normalize_service_account_info(info)["private_key"] == "line1\nline2"


class TestBuildVertexCredentials:
    @patch("src.app.services.gcp_credentials.service_account.Credentials.from_service_account_info")
    def test_builds_from_inline_json(self, mock_from_info):
        mock_from_info.return_value = MagicMock()
        settings = MagicMock()
        settings.parsed_gcp_service_account.return_value = dict(_FAKE_SA)

        creds = build_vertex_credentials(settings)

        assert creds is mock_from_info.return_value
        passed_info = mock_from_info.call_args.args[0]
        assert "\n" in passed_info["private_key"]
        assert "\\n" not in passed_info["private_key"]

    def test_raises_when_no_credentials(self):
        settings = MagicMock()
        settings.parsed_gcp_service_account.return_value = None

        with pytest.raises(AIServiceError):
            build_vertex_credentials(settings)


class TestVerifyVertexConnection:
    @patch("src.app.services.gcp_credentials.build_vertex_credentials")
    def test_refreshes_credentials(self, mock_build):
        mock_creds = MagicMock()
        mock_build.return_value = mock_creds
        settings = MagicMock()

        verify_vertex_connection(settings)

        mock_creds.refresh.assert_called_once()


class TestVertexAuthLabel:
    def test_labels_inline_json(self):
        settings = MagicMock()
        settings.parsed_gcp_service_account.return_value = _FAKE_SA
        label = vertex_auth_label(settings)
        assert "service_account_json" in label
        assert "caepy-plus@" in label

    def test_labels_none_when_unconfigured(self):
        settings = MagicMock()
        settings.parsed_gcp_service_account.return_value = None
        assert vertex_auth_label(settings) == "none"
