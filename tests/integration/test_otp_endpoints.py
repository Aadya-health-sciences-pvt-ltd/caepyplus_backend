"""Integration tests for OTP auth endpoints.

Uses the ``client`` fixture from ``tests/conftest.py`` which wires the FastAPI
app to an in-memory SQLite DB and provides an ``AsyncClient``.

The OTP service is mocked via ``app.dependency_overrides`` so no real SMS is
sent and no Redis is required.

Endpoints tested:
  POST /api/v1/auth/otp/request   — send OTP
  POST /api/v1/auth/otp/verify    — verify OTP + issue JWT
  POST /api/v1/auth/otp/resend    — resend OTP
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.app.main import app
from src.app.services.otp_service import get_otp_service


# ---------------------------------------------------------------------------
# Helpers / constants
# ---------------------------------------------------------------------------

REQUEST_URL = "/api/v1/auth/otp/request"
VERIFY_URL = "/api/v1/auth/otp/verify"
RESEND_URL = "/api/v1/auth/otp/resend"

VALID_MOBILE = "9876543210"
VALID_MOBILE_NORMALISED = "9876543210"


def _mock_otp_service(
    *,
    send_result: tuple[bool, str] = (True, "OTP sent successfully"),
    verify_result: tuple[bool, str] = (True, "OTP verified"),
) -> MagicMock:
    """Return a mock OTPService configured with the given send/verify outcomes."""
    mock = MagicMock()
    mock.send_otp = AsyncMock(return_value=send_result)
    mock.verify_otp = AsyncMock(return_value=verify_result)
    mock.mask_mobile = MagicMock(side_effect=lambda m: f"****{m[-4:]}")
    mock.settings = MagicMock()
    mock.settings.OTP_EXPIRY_SECONDS = 300
    return mock


@contextmanager
def _override_otp_service(mock_svc: MagicMock):
    """Context manager to override the OTP service via FastAPI dependency_overrides."""
    app.dependency_overrides[get_otp_service] = lambda: mock_svc
    try:
        yield mock_svc
    finally:
        app.dependency_overrides.pop(get_otp_service, None)


# ---------------------------------------------------------------------------
# POST /auth/otp/request
# ---------------------------------------------------------------------------


class TestRequestOtp:
    async def test_returns_200_on_success(self, client: AsyncClient):
        mock_svc = _mock_otp_service()
        with _override_otp_service(mock_svc):
            resp = await client.post(REQUEST_URL, json={"mobile_number": VALID_MOBILE})
        assert resp.status_code == 200

    async def test_response_body_has_success_true(self, client: AsyncClient):
        mock_svc = _mock_otp_service()
        with _override_otp_service(mock_svc):
            resp = await client.post(REQUEST_URL, json={"mobile_number": VALID_MOBILE})
        data = resp.json()
        assert data["success"] is True

    async def test_response_contains_masked_mobile(self, client: AsyncClient):
        mock_svc = _mock_otp_service()
        with _override_otp_service(mock_svc):
            resp = await client.post(REQUEST_URL, json={"mobile_number": VALID_MOBILE})
        data = resp.json()
        assert "mobile_number" in data
        # The real number must NOT appear verbatim in the response
        assert VALID_MOBILE not in data["mobile_number"]

    async def test_returns_500_when_send_fails(self, client: AsyncClient):
        mock_svc = _mock_otp_service(send_result=(False, "SMS gateway error"))
        with _override_otp_service(mock_svc):
            resp = await client.post(REQUEST_URL, json={"mobile_number": VALID_MOBILE})
        assert resp.status_code == 500

    async def test_returns_422_for_invalid_mobile(self, client: AsyncClient):
        """Pydantic validation rejects a non-Indian mobile number."""
        mock_svc = _mock_otp_service()
        with _override_otp_service(mock_svc):
            resp = await client.post(REQUEST_URL, json={"mobile_number": "123"})
        assert resp.status_code == 422

    async def test_returns_422_for_missing_field(self, client: AsyncClient):
        mock_svc = _mock_otp_service()
        with _override_otp_service(mock_svc):
            resp = await client.post(REQUEST_URL, json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/otp/verify
# ---------------------------------------------------------------------------


class TestVerifyOtp:
    async def test_returns_200_on_valid_otp(self, client: AsyncClient):
        mock_svc = _mock_otp_service(verify_result=(True, "OTP verified"))
        with _override_otp_service(mock_svc):
            resp = await client.post(
                VERIFY_URL,
                json={"mobile_number": VALID_MOBILE, "otp": "123456"},
            )
        assert resp.status_code == 200

    async def test_response_contains_access_token(self, client: AsyncClient):
        mock_svc = _mock_otp_service(verify_result=(True, "OTP verified"))
        with _override_otp_service(mock_svc):
            resp = await client.post(
                VERIFY_URL,
                json={"mobile_number": VALID_MOBILE, "otp": "123456"},
            )
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_access_token_is_valid_jwt(self, client: AsyncClient):
        """The returned token must be a 3-segment HS256 JWT."""
        mock_svc = _mock_otp_service(verify_result=(True, "OTP verified"))
        with _override_otp_service(mock_svc):
            resp = await client.post(
                VERIFY_URL,
                json={"mobile_number": VALID_MOBILE, "otp": "123456"},
            )
        token = resp.json()["access_token"]
        assert len(token.split(".")) == 3, "JWT must have 3 dot-separated segments"

    async def test_is_new_user_true_on_first_login(self, client: AsyncClient):
        mock_svc = _mock_otp_service(verify_result=(True, "OTP verified"))
        with _override_otp_service(mock_svc):
            resp = await client.post(
                VERIFY_URL,
                json={"mobile_number": "9700000001", "otp": "000000"},
            )
        assert resp.json()["is_new_user"] is True

    async def test_is_new_user_false_on_second_login(self, client: AsyncClient):
        """Verifying twice with the same number must return is_new_user=False second time."""
        mock_svc = _mock_otp_service(verify_result=(True, "OTP verified"))
        with _override_otp_service(mock_svc):
            await client.post(
                VERIFY_URL,
                json={"mobile_number": "9700000002", "otp": "000000"},
            )
            resp2 = await client.post(
                VERIFY_URL,
                json={"mobile_number": "9700000002", "otp": "000000"},
            )
        assert resp2.json()["is_new_user"] is False

    async def test_returns_401_for_invalid_otp(self, client: AsyncClient):
        mock_svc = _mock_otp_service(verify_result=(False, "Invalid OTP"))
        with _override_otp_service(mock_svc):
            resp = await client.post(
                VERIFY_URL,
                json={"mobile_number": VALID_MOBILE, "otp": "000000"},
            )
        assert resp.status_code == 401

    async def test_returns_401_for_expired_otp(self, client: AsyncClient):
        mock_svc = _mock_otp_service(verify_result=(False, "OTP has expired"))
        with _override_otp_service(mock_svc):
            resp = await client.post(
                VERIFY_URL,
                json={"mobile_number": VALID_MOBILE, "otp": "111111"},
            )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error_code"] == "OTP_EXPIRED"

    async def test_returns_422_for_invalid_mobile(self, client: AsyncClient):
        mock_svc = _mock_otp_service()
        with _override_otp_service(mock_svc):
            resp = await client.post(
                VERIFY_URL,
                json={"mobile_number": "0000000000", "otp": "123456"},
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/otp/resend
# ---------------------------------------------------------------------------


class TestResendOtp:
    async def test_returns_200_on_success(self, client: AsyncClient):
        mock_svc = _mock_otp_service(send_result=(True, "OTP resent successfully"))
        with _override_otp_service(mock_svc):
            resp = await client.post(RESEND_URL, json={"mobile_number": VALID_MOBILE})
        assert resp.status_code == 200

    async def test_response_body_has_success_true(self, client: AsyncClient):
        mock_svc = _mock_otp_service(send_result=(True, "OTP resent successfully"))
        with _override_otp_service(mock_svc):
            resp = await client.post(RESEND_URL, json={"mobile_number": VALID_MOBILE})
        assert resp.json()["success"] is True

    async def test_returns_500_when_resend_fails(self, client: AsyncClient):
        mock_svc = _mock_otp_service(send_result=(False, "Gateway timeout"))
        with _override_otp_service(mock_svc):
            resp = await client.post(RESEND_URL, json={"mobile_number": VALID_MOBILE})
        assert resp.status_code == 500
