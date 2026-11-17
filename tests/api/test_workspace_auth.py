"""Workspace identity vs select auth + webhook (no Bearer)."""
from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.app.linq360.config.auth import (
    require_dashboard_webhook_auth,
    require_identity_auth,
    require_workspace_select_auth,
)


def _jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.sig"


@pytest.mark.asyncio
async def test_require_identity_auth_ok_with_ph_user_id() -> None:
    token = _jwt(
        {
            "ph_user_id": "893",
            "ws_user_id": "327",
            "email": "demo1testing@gmail.com",
            "user_type": "doctor",
        }
    )
    db = AsyncMock()
    auth = await require_identity_auth(db=db, authorization=f"Bearer {token}")
    assert auth.linqmd_user_id == "893"
    assert auth.ws_user_id == 327
    assert auth.workspace_id is None
    assert auth.authorization.startswith("Bearer ")
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_require_identity_auth_falls_back_to_appointment_doctor_id() -> None:
    token = _jwt({"appointment_doctor_id": "892", "user_id": "325"})
    auth = await require_identity_auth(db=AsyncMock(), authorization=f"Bearer {token}")
    assert auth.linqmd_user_id == "892"
    assert auth.ws_user_id == 325


@pytest.mark.asyncio
async def test_require_identity_auth_missing() -> None:
    with pytest.raises(HTTPException) as exc:
        await require_identity_auth(db=AsyncMock(), authorization=None)
    assert exc.value.status_code == 401
    assert "identity_access_token" in str(exc.value.detail)


def test_require_workspace_select_auth_ok() -> None:
    token = _jwt(
        {
            "appointment_doctor_id": "892",
            "user_id": "325",
            "workspace_id": "161",
        }
    )
    auth = require_workspace_select_auth(authorization=f"Bearer {token}")
    assert auth.linqmd_user_id == "892"
    assert auth.ws_user_id == 325
    assert auth.workspace_id == 161
    assert auth.authorization.startswith("Bearer ")


def test_require_workspace_select_auth_requires_workspace_id() -> None:
    token = _jwt({"ph_user_id": "892", "ws_user_id": "325"})
    with pytest.raises(HTTPException) as exc:
        require_workspace_select_auth(authorization=f"Bearer {token}")
    assert exc.value.status_code == 401
    assert "workspace_id" in str(exc.value.detail)


def test_require_workspace_select_auth_missing() -> None:
    with pytest.raises(HTTPException) as exc:
        require_workspace_select_auth(authorization=None)
    assert exc.value.status_code == 401
    assert "workspace_access_token_main" in str(exc.value.detail)


def test_require_workspace_select_auth_no_doctor() -> None:
    token = _jwt({"user_id": "320", "workspace_id": "161", "appointment_doctor_id": None})
    with pytest.raises(HTTPException) as exc:
        require_workspace_select_auth(authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


def test_webhook_auth_allows_when_allowlist_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.app.linq360.config.auth.workspace_auth.ai_suggestions_open_domains",
        lambda: [],
    )
    request = MagicMock()
    request.headers = {}
    assert require_dashboard_webhook_auth(request) is None


def test_webhook_auth_requires_open_domain_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.app.linq360.config.auth.workspace_auth.ai_suggestions_open_domains",
        lambda: ["https://dev1.linqmd.com"],
    )
    request = MagicMock()
    request.headers = {"origin": "https://evil.example"}
    with pytest.raises(HTTPException) as exc:
        require_dashboard_webhook_auth(request)
    assert exc.value.status_code == 401

    request.headers = {"origin": "https://dev1.linqmd.com"}
    assert require_dashboard_webhook_auth(request) is None
