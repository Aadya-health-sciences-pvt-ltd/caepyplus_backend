"""Unit tests for otp endpoints (request, verify, google)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

from src.app.main import app
from src.app.services.otp_service import get_otp_service


@contextmanager
def _override_otp_service(mock_svc: MagicMock):
    """Context manager to override the OTP service via FastAPI dependency_overrides."""
    app.dependency_overrides[get_otp_service] = lambda: mock_svc
    try:
        yield mock_svc
    finally:
        app.dependency_overrides.pop(get_otp_service, None)


def _mock_otp_service(
    *,
    send_result: tuple[bool, str] = (True, "OTP sent successfully"),
    verify_result: tuple[bool, str] = (True, "OTP verified"),
) -> MagicMock:
    """Return a configured mock OTPService."""
    mock = MagicMock()
    mock.send_otp = AsyncMock(return_value=send_result)
    mock.verify_otp = AsyncMock(return_value=verify_result)
    mock.mask_mobile = MagicMock(side_effect=lambda m: f"****{m[-4:]}")
    mock.settings = MagicMock()
    mock.settings.OTP_EXPIRY_SECONDS = 300
    return mock

@pytest.mark.asyncio
async def test_request_otp(client: AsyncClient) -> None:
    """Test OTP request."""
    # We patch the service so it doesn't try connecting to external SMS or Redis logic if possible
    # But since it falls back to in-memory, we can just test the endpoint directly.
    payload = {"mobile_number": "9876543210"}
    with patch("src.app.services.otp_service.OTPService.send_otp") as mock_send:
        mock_send.return_value = (True, "OTP Sent")
        response = await client.post("/api/v1/auth/otp/request", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["success"] is True

@pytest.mark.asyncio
async def test_verify_otp(client: AsyncClient) -> None:
    """Test OTP verify."""
    payload = {"mobile_number": "9876543210", "otp": "999999"}
    with patch("src.app.services.otp_service.OTPService.verify_otp") as mock_verify:
        mock_verify.return_value = (True, "OTP Verified")

        response = await client.post("/api/v1/auth/otp/verify", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["success"] is True
    assert "access_token" in data["data"]

@pytest.mark.asyncio
async def test_resend_otp(client: AsyncClient) -> None:
    """Test OTP resend."""
    payload = {"mobile_number": "9876543210"}
    with patch("src.app.services.otp_service.OTPService.send_otp") as mock_send:
        mock_send.return_value = (True, "OTP Resent")
        response = await client.post("/api/v1/auth/otp/resend", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["success"] is True

@pytest.mark.asyncio
async def test_verify_admin_otp(client: AsyncClient) -> None:
    """Test admin OTP verify — mock OTP service so no Redis is needed."""
    mock_svc = _mock_otp_service(verify_result=(True, "OTP verified"))
    # The conftest seeds an admin user with phone "+919999999999"
    payload = {"mobile_number": "+919999999999", "otp": "123456"}
    with _override_otp_service(mock_svc):
        response = await client.post("/api/v1/auth/admin/otp/verify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["role"] == "admin"

@pytest.mark.asyncio
async def test_google_verify(client: AsyncClient, mock_firebase) -> None:
    """Test Google sign-in verify."""
    # The mock_firebase fixture in conftest.py mocks verify_firebase_token.
    payload = {"id_token": "valid_mock_token"}
    response = await client.post("/api/v1/auth/google/verify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["success"] is True
    assert "access_token" in data["data"]
    # The default mock_firebase email is test@example.com
    assert data["data"]["role"] == "user"
