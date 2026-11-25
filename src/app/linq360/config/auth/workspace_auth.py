"""LinQ360 identity / select / webhook auth deps."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, Request, status
from sqlalchemy import select

from ....db.session import DbSession
from ....repositories.doctor_repository import DoctorRepository
from ....repositories.linqmd_credentials_repository import LinqmdCredentialsRepository
from ...common.open_domains import request_matches_open_domain
from ...models.dashboard import DoctorDashboard, WorkspaceDoctorDashboard
from ...services.practice_hub_pending_client import (
    PracticeHubPendingError,
    workspace_identity_from_token,
)
from ..settings import ai_suggestions_open_domains


@dataclass(frozen=True, slots=True)
class WorkspaceSelectAuth:
    """Resolved workspace token + portal / Practice Hub identity."""

    authorization: str
    linqmd_user_id: str
    workspace_id: int | None
    ws_user_id: int | None


# Alias kept for docs / call sites that mean identity (login) token.
WorkspaceIdentityAuth = WorkspaceSelectAuth


async def _enrich_ph_user_id(
    db: DbSession,
    *,
    ph_user_id: str | None,
    ws_user_id: int | None,
    email: str | None,
) -> str:
    """Resolve Practice Hub uid: claims → ws mapping → email."""
    if ph_user_id:
        return str(ph_user_id).strip()

    if ws_user_id is not None:
        doctor_row = (
            await db.execute(
                select(DoctorDashboard.ph_user_id).where(
                    DoctorDashboard.ws_user_id == int(ws_user_id),
                    DoctorDashboard.ph_user_id.is_not(None),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if doctor_row is not None:
            return str(doctor_row)

        workspace_row = (
            await db.execute(
                select(WorkspaceDoctorDashboard.ph_user_id).where(
                    WorkspaceDoctorDashboard.ws_user_id == int(ws_user_id),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if workspace_row is not None:
            return str(workspace_row)

    if email:
        doctor = await DoctorRepository(db).get_by_email(email)
        if doctor is not None:
            creds = await LinqmdCredentialsRepository(db).get_by_doctor_id(int(doctor.id))
            if creds is not None and creds.linqmd_user_id:
                return str(creds.linqmd_user_id).strip()

    raise PracticeHubPendingError(
        "Could not resolve ph_user_id from token "
        "(ph_user_id / appointment_doctor_id / ws_user_id mapping / email)",
        status_code=401,
    )


async def require_identity_auth(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> WorkspaceIdentityAuth:
    """Require ``Authorization: Bearer <identity_access_token>`` (login JWT)."""
    if not authorization or not str(authorization).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authentication required. "
                "Pass Authorization: Bearer <identity_access_token> "
                "(from POST /auth/workspace/login)"
            ),
        )
    header = str(authorization).strip()
    try:
        identity = workspace_identity_from_token(
            header,
            require_ph_user_id=False,
            require_workspace_id=False,
        )
        ph = await _enrich_ph_user_id(
            db,
            ph_user_id=identity.get("ph_user_id") or identity.get("linqmd_user_id"),
            ws_user_id=identity.get("ws_user_id"),
            email=identity.get("email"),
        )
    except PracticeHubPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return WorkspaceIdentityAuth(
        authorization=header,
        linqmd_user_id=str(ph),
        workspace_id=identity.get("workspace_id"),
        ws_user_id=identity.get("ws_user_id"),
    )


def require_workspace_select_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> WorkspaceSelectAuth:
    """Require ``Authorization: Bearer <workspace_access_token_main>`` (select JWT)."""
    if not authorization or not str(authorization).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authentication required. "
                "Pass Authorization: Bearer <workspace_access_token_main> "
                "(from POST /auth/workspace/select)"
            ),
        )
    header = str(authorization).strip()
    try:
        identity = workspace_identity_from_token(
            header,
            require_ph_user_id=True,
            require_workspace_id=True,
        )
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


def require_dashboard_webhook_auth(request: Request) -> None:
    """Webhook: no Bearer; optional Origin/Referer allowlist."""
    allowlist = ai_suggestions_open_domains()
    if not allowlist:
        return

    domain_ok = request_matches_open_domain(
        request.headers.get("origin"),
        request.headers.get("referer"),
        allowlist,
    )
    if domain_ok:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Webhook Origin/Referer must match AI_SUGGESTIONS_OPEN_DOMAINS "
            "(no Bearer token; pass ph_user_id, ws_user_id, workspace_id in body)."
        ),
    )
