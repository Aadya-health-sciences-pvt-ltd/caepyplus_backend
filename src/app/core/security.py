"""Security helpers for JWT-based authentication.

Provides a FastAPI dependency to require a valid access token
on protected endpoints and helpers to decode/verify JWTs
created by the auth endpoints.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Request

from .config import Settings, get_settings
from .exceptions import UnauthorizedError


def _base64url_decode(data: str) -> bytes:
    """Decode a base64url-encoded string, handling missing padding."""

    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _decode_jwt(token: str, *, settings: Settings) -> dict[str, Any]:
    """Decode and validate an HS256 JWT.

    Mirrors the encoding used in auth._encode_jwt:
    - Verifies signature with SECRET_KEY
    - Ensures algorithm is HS256
    - Checks the exp claim against current UTC time
    """

    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:  # not enough / too many segments
        raise UnauthorizedError(
            message="Invalid token format",
            error_code="INVALID_TOKEN",
        ) from exc

    # Recompute signature
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")

    # Constant-time comparison
    if not hmac.compare_digest(signature_b64, expected_sig_b64):
        raise UnauthorizedError(
            message="Invalid token signature",
            error_code="INVALID_TOKEN",
        )

    # Decode payload
    try:
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes)
    except Exception as exc:  # pragma: no cover - defensive
        raise UnauthorizedError(
            message="Invalid token payload",
            error_code="INVALID_TOKEN",
        ) from exc

    # Check expiration
    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise UnauthorizedError(
            message="Invalid token expiration",
            error_code="INVALID_TOKEN",
        )

    now_ts = int(datetime.now(UTC).timestamp())
    if now_ts >= exp:
        raise UnauthorizedError(
            message="Token has expired",
            error_code="TOKEN_EXPIRED",
        )

    return payload  # type: ignore[no-any-return]


async def require_authentication(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """FastAPI dependency that enforces a valid Bearer token.

    Returns the token subject ("sub" claim) if validation succeeds.
    """

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise UnauthorizedError(
            message="Missing or invalid Authorization header",
            error_code="UNAUTHORIZED",
        )

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedError(
            message="Missing access token",
            error_code="UNAUTHORIZED",
        )

    payload = _decode_jwt(token, settings=settings)

    # Prefer internal doctor_id if present (as it is the DB primary key)
    # Default to 'sub' for backward compatibility or other users
    doc_id = payload.get("doctor_id")
    if doc_id is not None:
        return str(doc_id)

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise UnauthorizedError(
            message="Invalid token subject",
            error_code="INVALID_TOKEN",
        )

    return subject
