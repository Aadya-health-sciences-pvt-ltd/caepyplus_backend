"""Shared workspace-select Bearer auth for LinQ360 glance endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, status

from ..services.practice_hub_pending_client import (
    PracticeHubPendingError,
    linqmd_user_id_from_workspace_token,
)


@dataclass(frozen=True, slots=True)
class WorkspaceSelectAuth:
    """Resolved workspace select token + Drupal doctor uid."""

    authorization: str
    linqmd_user_id: str


def require_workspace_select_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> WorkspaceSelectAuth:
    """Require ``Authorization: Bearer <workspace_select_token>``.

    Doctor Drupal uid comes from ``appointment_doctor_id`` in the JWT.
    Used by both glance GET and glance sync (DRY).
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
        linqmd_user_id = linqmd_user_id_from_workspace_token(header)
    except PracticeHubPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return WorkspaceSelectAuth(authorization=header, linqmd_user_id=linqmd_user_id)
