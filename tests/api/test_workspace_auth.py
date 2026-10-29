"""Workspace select auth dependency for glance endpoints."""
from __future__ import annotations

import base64
import json

import pytest
from fastapi import HTTPException

from src.app.linq360.config.auth import require_workspace_select_auth


def _jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.sig"


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


def test_require_workspace_select_auth_missing() -> None:
    with pytest.raises(HTTPException) as exc:
        require_workspace_select_auth(authorization=None)
    assert exc.value.status_code == 401


def test_require_workspace_select_auth_no_doctor() -> None:
    token = _jwt({"user_id": "320", "appointment_doctor_id": None})
    with pytest.raises(HTTPException) as exc:
        require_workspace_select_auth(authorization=f"Bearer {token}")
    assert exc.value.status_code == 401
