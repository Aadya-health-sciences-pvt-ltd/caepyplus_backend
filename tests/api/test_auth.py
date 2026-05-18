"""Tests for auth endpoints.

Current API surface:
  POST /api/v1/auth/otp/request       — send OTP to mobile number
  POST /api/v1/auth/otp/verify        — verify OTP and get JWT (doctor flow)
  POST /api/v1/auth/otp/resend        — resend OTP
  POST /api/v1/auth/admin/otp/verify  — verify OTP for admin/operational user
  POST /api/v1/auth/google/verify     — Google Sign-In via Firebase token

NOTE: There is no /admin/login/mimic endpoint in the current codebase.
      The admin OTP verify flow is POST /api/v1/auth/admin/otp/verify.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


# ---------------------------------------------------------------------------
# POST /api/v1/auth/otp/request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_request_success(client: AsyncClient) -> None:
    """OTP request endpoint sends OTP and returns 200 with masked number."""
    with patch(
        "src.app.services.otp_service.OTPService.send_otp",
        new_callable=AsyncMock,
        return_value=(True, "OTP sent successfully"),
    ):
        payload = {"mobile_number": "9999999999"}
        response = await client.post("/api/v1/auth/otp/request", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "mobile_number" in data
    assert "expires_in_seconds" in data


@pytest.mark.asyncio
async def test_otp_request_send_failure_returns_500(client: AsyncClient) -> None:
    """If OTP send fails, endpoint returns 500."""
    with patch(
        "src.app.services.otp_service.OTPService.send_otp",
        new_callable=AsyncMock,
        return_value=(False, "SMS provider unavailable"),
    ):
        payload = {"mobile_number": "9999999999"}
        response = await client.post("/api/v1/auth/otp/request", json=payload)
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/v1/auth/otp/verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_verify_success(client: AsyncClient) -> None:
    """Successful OTP verification returns access_token and doctor_id."""
    with patch(
        "src.app.services.otp_service.OTPService.verify_otp",
        new_callable=AsyncMock,
        return_value=(True, "OTP verified"),
    ):
        payload = {"mobile_number": "9999999999", "otp": "123456"}
        response = await client.post("/api/v1/auth/otp/verify", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data
    assert "doctor_id" in data
    assert "role" in data


@pytest.mark.asyncio
async def test_otp_verify_invalid_otp_returns_401(client: AsyncClient) -> None:
    """Invalid OTP returns 401 Unauthorized."""
    with patch(
        "src.app.services.otp_service.OTPService.verify_otp",
        new_callable=AsyncMock,
        return_value=(False, "Invalid OTP"),
    ):
        payload = {"mobile_number": "9999999999", "otp": "000000"}
        response = await client.post("/api/v1/auth/otp/verify", json=payload)

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["success"] is False


@pytest.mark.asyncio
async def test_otp_verify_expired_otp_returns_401(client: AsyncClient) -> None:
    """Expired OTP returns 401 with OTP_EXPIRED error code."""
    with patch(
        "src.app.services.otp_service.OTPService.verify_otp",
        new_callable=AsyncMock,
        return_value=(False, "OTP has expired"),
    ):
        payload = {"mobile_number": "9999999999", "otp": "123456"}
        response = await client.post("/api/v1/auth/otp/verify", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == "OTP_EXPIRED"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/otp/resend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_resend_success(client: AsyncClient) -> None:
    """Resend OTP returns 200 and masked mobile number."""
    with patch(
        "src.app.services.otp_service.OTPService.send_otp",
        new_callable=AsyncMock,
        return_value=(True, "OTP sent successfully"),
    ):
        payload = {"mobile_number": "9999999999"}
        response = await client.post("/api/v1/auth/otp/resend", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "OTP resent successfully"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/admin/otp/verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_otp_verify_success(client: AsyncClient) -> None:
    """Admin OTP verify returns access_token for pre-seeded admin user."""
    # The admin user (+919999999999) is seeded by the client fixture
    with patch(
        "src.app.services.otp_service.OTPService.verify_otp",
        new_callable=AsyncMock,
        return_value=(True, "OTP verified"),
    ):
        payload = {"mobile_number": "+919999999999", "otp": "123456"}
        response = await client.post("/api/v1/auth/admin/otp/verify", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_admin_otp_verify_invalid_otp_returns_400(client: AsyncClient) -> None:
    """Invalid OTP for admin verify returns 400 Bad Request."""
    with patch(
        "src.app.services.otp_service.OTPService.verify_otp",
        new_callable=AsyncMock,
        return_value=(False, "Invalid OTP"),
    ):
        payload = {"mobile_number": "+919999999999", "otp": "000000"}
        response = await client.post("/api/v1/auth/admin/otp/verify", json=payload)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_otp_verify_nonexistent_user_returns_403(client: AsyncClient) -> None:
    """Admin OTP verify for non-existent user returns 403."""
    with patch(
        "src.app.services.otp_service.OTPService.verify_otp",
        new_callable=AsyncMock,
        return_value=(True, "OTP verified"),
    ):
        payload = {"mobile_number": "+919000000001", "otp": "123456"}
        response = await client.post("/api/v1/auth/admin/otp/verify", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "USER_NOT_FOUND"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/google/verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_google_verify_success(client: AsyncClient, mock_firebase: None) -> None:
    """Google Sign-In returns access_token on valid Firebase token."""
    payload = {"id_token": "mock_firebase_id_token"}
    response = await client.post("/api/v1/auth/google/verify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data


@pytest.mark.asyncio
async def test_google_verify_invalid_token_returns_401(client: AsyncClient) -> None:
    """Invalid Firebase token returns 401."""
    with patch(
        "src.app.core.firebase_config.verify_firebase_token",
        new_callable=AsyncMock,
        side_effect=ValueError("Invalid token"),
    ):
        payload = {"id_token": "bad_token"}
        response = await client.post("/api/v1/auth/google/verify", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == "INVALID_FIREBASE_TOKEN"
