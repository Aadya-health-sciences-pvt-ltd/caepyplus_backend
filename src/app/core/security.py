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

import jwt as pyjwt
from fastapi import Depends, Request
from jwt import PyJWKClient

from .config import Settings, get_settings
from .exceptions import UnauthorizedError

_jwks_clients: dict[str, PyJWKClient] = {}


def _base64url_decode(data: str) -> bytes:
    """Decode a base64url-encoded string, handling missing padding."""

    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _decode_jwt_header_alg(token: str) -> str | None:
    """Unverified structural peek only, to route to the right verifier below.
    Real verification (signature/exp/aud/iss) always happens after this."""

    try:
        header_b64 = token.split(".")[0]
        header = json.loads(_base64url_decode(header_b64))
    except Exception:
        return None
    return header.get("alg") if isinstance(header, dict) else None


def _get_jwks_client(issuer: str) -> PyJWKClient:
    client = _jwks_clients.get(issuer)
    if client is None:
        client = PyJWKClient(f"{issuer}/jwks", cache_keys=True)
        _jwks_clients[issuer] = client
    return client


def _decode_oidc_jwt(token: str, *, settings: Settings) -> dict[str, Any]:
    """Verifies an RS256 OIDC access token against linqmd_workspace_backend_code's
    JWKS: signature, expiry, issuer, and audience (scoped to this service's own
    resource identifier - what makes a token minted for another service unusable
    here)."""

    assert settings.OIDC_ISSUER  # guarded by caller
    try:
        signing_key = _get_jwks_client(settings.OIDC_ISSUER).get_signing_key_from_jwt(token)
        return pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.OIDC_ISSUER,
            audience=settings.OIDC_AUDIENCE,
        )
    except pyjwt.PyJWTError as exc:
        raise UnauthorizedError(
            message="Invalid or expired token",
            error_code="INVALID_TOKEN",
        ) from exc


def _decode_hs256_with_secret(token: str, *, secret: str) -> dict[str, Any]:
    """Verify one HS256 JWT against ``secret`` (signature + exp)."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise UnauthorizedError(
            message="Invalid token format",
            error_code="INVALID_TOKEN",
        ) from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")

    if not hmac.compare_digest(signature_b64, expected_sig_b64):
        raise UnauthorizedError(
            message="Invalid token signature",
            error_code="INVALID_TOKEN",
        )

    try:
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes)
    except Exception as exc:  # pragma: no cover - defensive
        raise UnauthorizedError(
            message="Invalid token payload",
            error_code="INVALID_TOKEN",
        ) from exc

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


def _decode_jwt(token: str, *, settings: Settings) -> dict[str, Any]:
    """Decode and validate a Bearer JWT.

    OIDC_ENABLED false/unset (default): HS256 against SECRET_KEY (Caepy login).
    When WORKSPACE_JWT_SECRET is set, also accepts workspace portal
    identity_access_token / workspace_access_token_main (same secret as
    Practice Hub workspace_jwt_secret).

    OIDC_ENABLED true: also accepts RS256 tokens issued by
    linqmd_workspace_backend_code's OIDC Authorization Server, routed by the
    token's own (unverified) alg header.
    """

    if settings.OIDC_ENABLED and settings.OIDC_ISSUER:
        alg = _decode_jwt_header_alg(token)
        if alg == "RS256":
            return _decode_oidc_jwt(token, settings=settings)

    try:
        return _decode_hs256_with_secret(token, secret=settings.SECRET_KEY)
    except UnauthorizedError as caepy_exc:
        workspace_secret = (settings.WORKSPACE_JWT_SECRET or "").strip()
        if not workspace_secret:
            raise caepy_exc
        if caepy_exc.error_code == "TOKEN_EXPIRED":
            raise caepy_exc
        try:
            return _decode_hs256_with_secret(token, secret=workspace_secret)
        except UnauthorizedError:
            raise caepy_exc from None


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
    if isinstance(subject, str) and subject.strip():
        return subject.strip()

    # Workspace identity_access_token: no ``sub`` — use email (never log it).
    email = payload.get("email")
    if isinstance(email, str) and "@" in email.strip():
        return email.strip().lower()

    raise UnauthorizedError(
        message="Invalid token subject",
        error_code="INVALID_TOKEN",
    )


def decode_bearer_jwt_from_request(request: Request, *, settings: Settings) -> dict[str, Any]:
    """Decode and validate the Bearer JWT from ``request`` (same rules as RBAC)."""

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise UnauthorizedError(
            message="Missing or invalid Authorization header",
            error_code="UNAUTHORIZED",
        )

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedError(message="Missing access token", error_code="UNAUTHORIZED")

    return _decode_jwt(token, settings=settings)


def subject_effective_doctor_id(
    user_doctor_id: int | None,
    token_payload: dict[str, Any],
) -> int | None:
    """Doctor id for self-service ownership checks.

    Prefer ``users.doctor_id``; if unset (legacy / partial rows), use the signed
    ``doctor_id`` claim from the JWT (Google / email-first login).
    """

    if user_doctor_id is not None:
        return user_doctor_id

    raw = token_payload.get("doctor_id")
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if s.isdigit():
            n = int(s)
            return n if n > 0 else None
    return None
