"""Shared workspace-select Bearer auth for LinQ360 glance endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, status

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
