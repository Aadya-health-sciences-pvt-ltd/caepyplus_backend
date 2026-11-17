"""Fetch Drupal pending counts from Practice Hub (identity / workspace token flow).

GET {LINQMD_PRACTICE_HUB_API_URL}/api/linq360/pending-counts

No user_id in the URL or body. Doctor comes from the Bearer token
(``ph_user_id`` / ``appointment_doctor_id``). CAEPY does not implement this GET;
it pulls the Drupal payload into doctor_dashboard.todays_glance via
POST /linq360/glance/sync, keeping both pending_count and id arrays.
"""
from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import jwt as pyjwt

from ...core.config import get_settings


class PracticeHubPendingError(Exception):
    """Practice Hub pending-counts call failed."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


PENDING_SOURCES = ("reviews", "blog_comments", "podcast_comments")

_SOURCE_ID_KEYS: dict[str, tuple[str, ...]] = {
    "reviews": ("review_id",),
    "blog_comments": ("comment_id", "blog_id"),
    "podcast_comments": ("comment_id", "podcast_id"),
}


def non_negative_int(value: object) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _id_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def pending_count_from_block(block: object) -> int:
    """Read pending_count from a Drupal content block."""
    if isinstance(block, dict):
        return non_negative_int(block.get("pending_count"))
    return non_negative_int(block)


def parse_source_block(source: str, block: object) -> dict[str, Any]:
    """Normalize one Drupal source block (count + id arrays)."""
    raw = block if isinstance(block, dict) else {"pending_count": block}
    entry: dict[str, Any] = {"pending_count": pending_count_from_block(raw)}
    for key in _SOURCE_ID_KEYS.get(source, ()):
        entry[key] = _id_list(raw.get(key))
    return entry


def parse_pending_payload(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map Drupal pending-counts JSON to three source blocks (counts + ids).

    Accepts:
    - ``{ "content": { reviews, blog_comments, podcast_comments } }``
    - envelope ``{ "status_code", "msg", "data": { "content": {...} } }``
    - flat ``{ reviews, blog_comments, podcast_comments }``
    """
    root: dict[str, Any] = body if isinstance(body, dict) else {}
    data = root.get("data")
    if isinstance(data, dict) and (
        isinstance(data.get("content"), dict)
        or any(name in data for name in PENDING_SOURCES)
    ):
        root = data
    source = root.get("content") if isinstance(root.get("content"), dict) else root
    if not isinstance(source, dict):
        source = {}
    return {name: parse_source_block(name, source.get(name)) for name in PENDING_SOURCES}


def parse_pending_counts(body: dict[str, Any]) -> dict[str, int]:
    """Map payload to the three pending counts only."""
    return {
        name: block["pending_count"] for name, block in parse_pending_payload(body).items()
    }


def _normalize_bearer_token(token: str) -> str:
    raw = (token or "").strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    return raw


def _optional_int_claim(claims: dict[str, Any], key: str) -> int | None:
    value = claims.get(key)
    if value is None or not str(value).strip():
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _optional_str_claim(claims: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = claims.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "none":
            return text
    return None


def resolve_ws_user_id_from_claims(claims: dict[str, Any]) -> int | None:
    """Portal user id: ``ws_user_id`` → ``user_id`` → ``id``."""
    for key in ("ws_user_id", "user_id", "id"):
        parsed = _optional_int_claim(claims, key)
        if parsed is not None:
            return parsed
    return None


def resolve_ph_user_id_from_claims(claims: dict[str, Any]) -> str | None:
    """Practice Hub Drupal uid: ``ph_user_id`` → ``appointment_doctor_id``."""
    return _optional_str_claim(claims, "ph_user_id", "appointment_doctor_id")


def decode_workspace_select_claims(token: str) -> dict[str, Any]:
    """Decode workspace HS256 JWT payload.

    When ``WORKSPACE_JWT_SECRET`` / ``workspace_jwt_secret`` is set, signature
    and expiry are verified (Practice Hub contract). Otherwise payload-only
    decode is used so local/dev can still forward the Bearer to Drupal.
    """
    raw = _normalize_bearer_token(token)
    if not raw or raw.count(".") < 2:
        raise PracticeHubPendingError("Workspace token is not a valid JWT")

    settings = get_settings()
    secret = (settings.WORKSPACE_JWT_SECRET or "").strip()
    if secret:
        try:
            claims = pyjwt.decode(
                raw,
                secret,
                algorithms=["HS256"],
                options={"require": ["exp"]},
            )
        except pyjwt.ExpiredSignatureError as exc:
            raise PracticeHubPendingError(
                "Workspace token has expired",
                status_code=401,
            ) from exc
        except pyjwt.PyJWTError as exc:
            raise PracticeHubPendingError(
                "Workspace token signature is invalid",
                status_code=401,
            ) from exc
        if not isinstance(claims, dict):
            raise PracticeHubPendingError("Workspace token payload was not an object")
        return claims

    parts = raw.split(".")
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
        claims = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise PracticeHubPendingError(
            "Workspace token payload could not be decoded"
        ) from exc
    if not isinstance(claims, dict):
        raise PracticeHubPendingError("Workspace token payload was not an object")
    return claims


def workspace_identity_from_token(
    token: str,
    *,
    require_ph_user_id: bool = True,
    require_workspace_id: bool = False,
) -> dict[str, Any]:
    """Identity claims from a workspace login (identity) or select JWT.

    Resolution order for Practice Hub doctor id:
    ``ph_user_id`` → ``appointment_doctor_id`` (DB / email enrichment happens
    in auth deps when claims omit both).

    Returns:
        linqmd_user_id / ph_user_id: Drupal doctor uid (string or None)
        workspace_id: portal workspace id, optional unless required
        ws_user_id: portal user id, optional
        email: claim email when present (for fallback mapping)
    """
    claims = decode_workspace_select_claims(token)
    ph = resolve_ph_user_id_from_claims(claims)
    ws_user_id = resolve_ws_user_id_from_claims(claims)
    workspace_id = _optional_int_claim(claims, "workspace_id")
    email_raw = claims.get("email")
    email = (
        str(email_raw).strip().lower()
        if isinstance(email_raw, str) and str(email_raw).strip()
        else None
    )

    if require_workspace_id and workspace_id is None:
        raise PracticeHubPendingError(
            "Workspace select token has no workspace_id "
            "(POST /auth/workspace/select first)",
            status_code=401,
        )

    if require_ph_user_id and not ph:
        raise PracticeHubPendingError(
            "Workspace token has no ph_user_id / appointment_doctor_id "
            "(map the doctor or use identity enrichment)",
            status_code=401,
        )

    return {
        "linqmd_user_id": ph,
        "ph_user_id": ph,
        "workspace_id": workspace_id,
        "ws_user_id": ws_user_id,
        "email": email,
    }


def linqmd_user_id_from_workspace_token(token: str) -> str:
    """Drupal doctor uid from ``ph_user_id`` / ``appointment_doctor_id``."""
    return str(workspace_identity_from_token(token)["linqmd_user_id"])


async def fetch_pending_counts(workspace_access_token: str) -> dict[str, dict[str, Any]]:
    """GET Practice Hub pending counts using the Bearer token (identity or select).

    URL has no user_id. Doctor is resolved by Drupal from the token.
    Returns normalized source blocks including id arrays.
    """
    settings = get_settings()
    base = (settings.LINQMD_PRACTICE_HUB_API_URL or "").strip()
    if not base:
        raise PracticeHubPendingError("LINQMD_PRACTICE_HUB_API_URL is not set")

    bearer = _normalize_bearer_token(workspace_access_token)
    if not bearer:
        raise PracticeHubPendingError(
            "Workspace access token is required",
            status_code=401,
        )

    url = settings.linqmd_practice_hub_url("/api/linq360/pending-counts")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer}",
    }
    if settings.LINQMD_PRACTICE_HUB_COOKIE:
        headers["Cookie"] = settings.LINQMD_PRACTICE_HUB_COOKIE

    try:
        async with httpx.AsyncClient(timeout=settings.LINQMD_API_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise PracticeHubPendingError(
            f"Practice Hub pending-counts request failed: {exc}"
        ) from exc

    if response.status_code == 401:
        raise PracticeHubPendingError(
            "Practice Hub pending-counts: Authentication required "
            "(use identity_access_token Bearer from workspace login)",
            status_code=401,
        )
    if response.status_code != 200:
        detail = response.text[:300]
        raise PracticeHubPendingError(
            f"Practice Hub pending-counts HTTP {response.status_code}: {detail}",
            status_code=response.status_code,
        )

    try:
        body = response.json()
    except Exception as exc:
        raise PracticeHubPendingError(
            "Practice Hub pending-counts response was not JSON"
        ) from exc
    if not isinstance(body, dict):
        raise PracticeHubPendingError(
            "Practice Hub pending-counts response was not an object"
        )
    return parse_pending_payload(body)
