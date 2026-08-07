"""Outbound OIDC client_credentials helper.

Resource indicators (token aud) are read only from env — never hardcoded:

  OIDC_RESOURCE_WORKSPACE
  OIDC_RESOURCE_AIMR
  OIDC_RESOURCE_PAYMENT
  OIDC_RESOURCE_CAEPY
  OIDC_RESOURCE_COMMUNICATION
  OIDC_RESOURCE_SYMPTOM_COLLECTOR
  OIDC_RESOURCE_CLINIC_BOT

Issuer / client: OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET.
"""
from __future__ import annotations

import base64
import os
import time
from typing import Optional

import httpx


class Resource:
    """Logical keys — resolve to URLs via OIDC_RESOURCE_* env vars."""

    WORKSPACE = "WORKSPACE"
    AIMR = "AIMR"
    PAYMENT = "PAYMENT"
    CAEPY = "CAEPY"
    COMMUNICATION = "COMMUNICATION"
    SYMPTOM_COLLECTOR = "SYMPTOM_COLLECTOR"
    CLINIC_BOT = "CLINIC_BOT"


_ENV_NAMES = {
    Resource.WORKSPACE: "OIDC_RESOURCE_WORKSPACE",
    Resource.AIMR: "OIDC_RESOURCE_AIMR",
    Resource.PAYMENT: "OIDC_RESOURCE_PAYMENT",
    Resource.CAEPY: "OIDC_RESOURCE_CAEPY",
    Resource.COMMUNICATION: "OIDC_RESOURCE_COMMUNICATION",
    Resource.SYMPTOM_COLLECTOR: "OIDC_RESOURCE_SYMPTOM_COLLECTOR",
    Resource.CLINIC_BOT: "OIDC_RESOURCE_CLINIC_BOT",
}

_DEFAULT_SCOPES = {
    Resource.WORKSPACE: "workspace.read workspace.write",
    Resource.AIMR: "aimr.read aimr.write",
    Resource.PAYMENT: "payment.read payment.write",
    Resource.COMMUNICATION: "communication.read communication.write",
    Resource.SYMPTOM_COLLECTOR: "symptom-collector.read symptom-collector.write",
    Resource.CAEPY: "caepy.read caepy.write",
    Resource.CLINIC_BOT: "clinic-bot.read clinic-bot.write",
}

_EXPIRY_SLACK_SECONDS = 30


def resolve_oidc_resource(key: str) -> Optional[str]:
    env_name = _ENV_NAMES.get(key)
    if not env_name:
        return None
    value = (os.environ.get(env_name) or "").strip()
    return value or None


class OidcHttpClient:
    def __init__(
        self,
        issuer: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ) -> None:
        self._issuer = (issuer or os.environ.get("OIDC_ISSUER") or "").rstrip("/")
        self._client_id = client_id or os.environ.get("OIDC_CLIENT_ID")
        self._client_secret = client_secret or os.environ.get("OIDC_CLIENT_SECRET")
        self._http = httpx.AsyncClient(timeout=10.0)
        self._tokens: dict[str, tuple[str, float]] = {}

    @property
    def _enabled(self) -> bool:
        return bool(self._issuer and self._client_id and self._client_secret)

    async def get_token(self, resource_key: str, scope: Optional[str] = None) -> Optional[str]:
        if not self._enabled:
            return None

        resource = resolve_oidc_resource(resource_key)
        if not resource:
            return None

        cached = self._tokens.get(resource)
        if cached and cached[1] > time.time() + _EXPIRY_SLACK_SECONDS:
            return cached[0]

        return await self._fetch_token(resource, scope or _DEFAULT_SCOPES.get(resource_key, ""))

    async def _fetch_token(self, resource: str, scope: str) -> str:
        credentials = f"{self._client_id}:{self._client_secret}".encode()
        basic_auth = base64.b64encode(credentials).decode()
        resp = await self._http.post(
            f"{self._issuer}/token",
            headers={
                "Authorization": f"Basic {basic_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "resource": resource,
                "scope": scope,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        access_token = body["access_token"]
        expires_in = body.get("expires_in", 600)
        self._tokens[resource] = (access_token, time.time() + expires_in)
        return access_token

    async def authorization_headers(
        self, resource_key: str, scope: Optional[str] = None
    ) -> dict:
        token = await self.get_token(resource_key, scope)
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    async def close(self) -> None:
        await self._http.aclose()


_oidc_http_client: Optional[OidcHttpClient] = None


def get_oidc_http_client() -> OidcHttpClient:
    global _oidc_http_client
    if _oidc_http_client is None:
        _oidc_http_client = OidcHttpClient()
    return _oidc_http_client
