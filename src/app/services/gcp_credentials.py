"""Build Google Cloud credentials for Vertex AI from settings."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from google.auth.transport.requests import Request
from google.oauth2 import service_account

from ..core.exceptions import AIServiceError

if TYPE_CHECKING:
    from ..core.config import Settings

logger = logging.getLogger(__name__)

_CLOUD_PLATFORM_SCOPE = ("https://www.googleapis.com/auth/cloud-platform",)


def normalize_service_account_info(info: dict[str, Any]) -> dict[str, Any]:
    """Normalize PEM newlines when JSON was injected with escaped \\n."""
    normalized = dict(info)
    private_key = normalized.get("private_key")
    if isinstance(private_key, str) and "\\n" in private_key:
        normalized["private_key"] = private_key.replace("\\n", "\n")
    return normalized


def vertex_auth_label(settings: Settings) -> str:
    """Safe log label for which Vertex auth source is active."""
    info = settings.parsed_gcp_service_account()
    if info:
        return f"service_account_json email={info.get('client_email', '<unknown>')}"
    return "none"


def build_vertex_credentials(settings: Settings) -> service_account.Credentials:
    """
    Build OAuth credentials for Vertex AI from GCP_SERVICE_ACCOUNT_JSON.

    Raises:
        AIServiceError: When Vertex was selected but inline JSON is missing/invalid.
    """
    info = settings.parsed_gcp_service_account()
    if info:
        creds = service_account.Credentials.from_service_account_info(
            normalize_service_account_info(info),
            scopes=list(_CLOUD_PLATFORM_SCOPE),
        )
        logger.debug(
            "Vertex credentials from GCP_SERVICE_ACCOUNT_JSON project=%s email=%s",
            info.get("project_id"),
            info.get("client_email"),
        )
        return creds

    raise AIServiceError(
        message="Vertex AI credentials not configured",
        original_error="Set GCP_SERVICE_ACCOUNT_JSON to a valid service account key",
    )


def verify_vertex_connection(settings: Settings) -> None:
    """Refresh OAuth token to confirm Vertex credentials can authenticate."""
    credentials = build_vertex_credentials(settings)
    credentials.refresh(Request())
