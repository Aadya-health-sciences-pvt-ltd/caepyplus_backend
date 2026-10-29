"""Shared workspace-select Bearer auth for LinQ360 glance endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from ...core.config import get_settings
from ..open_domains import parse_open_domains, request_matches_open_domain
from ..services.practice_hub_pending_client import (
    PracticeHubPendingError,
    workspace_identity_from_token,
)


@dataclass(frozen=True, slots=True)
class WorkspaceSelectAuth:
    """Resolved workspace select token + portal / Practice Hub identity."""

    authorization: str
    linqmd_user_id: str
    workspace_id: int | None
    ws_user_id: int | None


def require_workspace_select_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> WorkspaceSelectAuth:
    """Require ``Authorization: Bearer <workspace_select_token>``.

    Reads from the JWT:
    - ``appointment_doctor_id`` → ``ph_user_id`` / glance key (required)
    - ``workspace_id`` → ``workspace_id``
    - ``user_id`` → ``ws_user_id``
    """
    if not authorization or not str(authorization).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authentication required. "
                "Pass Authorization: Bearer <workspace_select_token>"
            ),
        )
    header = str(authorization).strip()
    try:
        identity = workspace_identity_from_token(header)
    except PracticeHubPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return WorkspaceSelectAuth(
        authorization=header,
        linqmd_user_id=str(identity["linqmd_user_id"]),
        workspace_id=identity.get("workspace_id"),
        ws_user_id=identity.get("ws_user_id"),
    )


def require_dashboard_webhook_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> WorkspaceSelectAuth:
    """Nest-style OR gate for dashboard webhook.

    - Trusted ``Origin`` / ``Referer`` (``AI_SUGGESTIONS_OPEN_DOMAINS``) bypasses
      the domain check, but this webhook still needs Bearer for doctor identity
      (body no longer carries ``ph_user_id`` / ``workspace_id`` / ``ws_user_id``).
    - Otherwise require a valid workspace select Bearer (same as glance).
    """
    settings = get_settings()
    allowlist = parse_open_domains(settings.AI_SUGGESTIONS_OPEN_DOMAINS)
    domain_ok = request_matches_open_domain(
        request.headers.get("origin"),
        request.headers.get("referer"),
        allowlist,
    )

    has_bearer = bool(authorization and str(authorization).strip())
    if has_bearer:
        return require_workspace_select_auth(authorization)

    if domain_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Trusted domain matched, but Authorization: Bearer "
                "<workspace_select_token> is required to identify the doctor "
                "(ph_user_id / workspace_id / ws_user_id come from the JWT)."
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Authentication required. "
            "Pass Authorization: Bearer <workspace_select_token>, "
            "or call from a trusted Origin/Referer listed in "
            "AI_SUGGESTIONS_OPEN_DOMAINS (Bearer still required for identity)."
        ),
    )
