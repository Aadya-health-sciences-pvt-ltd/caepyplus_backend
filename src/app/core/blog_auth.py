"""Resolve the doctor id for Blog Studio self-service routes."""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status

from .config import Settings, get_settings
from .rbac import _parse_jwt_doctor_id, get_current_user
from .security import decode_bearer_jwt_from_request, subject_effective_doctor_id
from ..db.session import DbSession

logger = logging.getLogger(__name__)


async def get_authenticated_doctor_id(
    request: Request,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> int:
    """Doctor pk for blog ownership — prefers ``users.doctor_id``, then JWT claim.

    ``require_authentication`` returns the JWT ``doctor_id`` claim first, which can
    disagree with the linked ``users`` row and cause false 404s on blog lookup.
    """
    user = await get_current_user(request, settings, db)
    payload = decode_bearer_jwt_from_request(request, settings=settings)
    doctor_id = subject_effective_doctor_id(user.doctor_id, payload)
    if doctor_id is None:
        doctor_id = _parse_jwt_doctor_id(payload.get("doctor_id"))
    if doctor_id is None:
        logger.warning(
            "blog_auth no_doctor_id user_id=%s role=%s sub=%r",
            user.id,
            user.role,
            payload.get("sub"),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No doctor profile linked to this account.",
        )

    claim = _parse_jwt_doctor_id(payload.get("doctor_id"))
    if claim is not None and claim != doctor_id:
        logger.warning(
            "blog_auth jwt_doctor_id_mismatch jwt_claim=%s effective=%s user_id=%s",
            claim,
            doctor_id,
            user.id,
        )

    return doctor_id


AuthenticatedDoctorId = Annotated[int, Depends(get_authenticated_doctor_id)]


def linqmd_login_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    msg = str(exc).lower()
    if "access_token" in msg:
        return "linqmd_login_response_invalid"
    return "linqmd_credentials_invalid"
