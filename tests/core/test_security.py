"""Tests for JWT security and authentication dependencies."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi import Request

from src.app.core.config import Settings
from src.app.core.exceptions import UnauthorizedError
from src.app.core.security import _decode_jwt, require_authentication


@pytest.fixture
def mock_settings():
    return Settings(SECRET_KEY="test-secret-key-that-is-at-least-32-characters", ENVIRONMENT="development")

def create_raw_token(payload: dict, secret: str = "test-secret-key-that-is-at-least-32-characters") -> str:
    header = {"alg": "HS256", "typ": "JWT"}

    def b64_encode(data: dict) -> str:
        js = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(js).rstrip(b"=").decode("ascii")

    encoded_header = b64_encode(header)
    encoded_payload = b64_encode(payload)

    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")

    return f"{signing_input.decode('ascii')}.{encoded_signature}"

def test_decode_jwt_success(mock_settings):
    """Test successful token decode."""
    now = int(datetime.now(UTC).timestamp())
    payload = {"sub": "+919999999999", "exp": now + 3600}
    token = create_raw_token(payload)

    decoded = _decode_jwt(token, settings=mock_settings)
    assert decoded["sub"] == "+919999999999"

def test_decode_jwt_expired(mock_settings):
    """Test expired token decode."""
    now = int(datetime.now(UTC).timestamp())
    payload = {"sub": "+919999999999", "exp": now - 3600}
    token = create_raw_token(payload)

    with pytest.raises(UnauthorizedError) as exc:
        _decode_jwt(token, settings=mock_settings)
    assert "expired" in str(exc.value).lower()

def test_decode_jwt_invalid_signature(mock_settings):
    """Test token decode with invalid signature."""
    now = int(datetime.now(UTC).timestamp())
    payload = {"sub": "+919999999999", "exp": now + 3600}
    token = create_raw_token(payload, secret="wrong-secret")

    with pytest.raises(UnauthorizedError) as exc:
        _decode_jwt(token, settings=mock_settings)
    assert "signature" in str(exc.value).lower()

def test_decode_jwt_invalid_format(mock_settings):
    """Test token decode with invalid format."""
    with pytest.raises(UnauthorizedError):
        _decode_jwt("not.a.token", settings=mock_settings)

def test_decode_jwt_invalid_exp(mock_settings):
    """Test token decode with invalid exp claim."""
    payload = {"sub": "+919999999999", "exp": "not-an-int"}
    token = create_raw_token(payload)

    with pytest.raises(UnauthorizedError) as exc:
        _decode_jwt(token, settings=mock_settings)
    assert "expiration" in str(exc.value).lower()

@pytest.mark.asyncio
async def test_require_authentication_success(mock_settings):
    """Test require_authentication dependency on success."""
    now = int(datetime.now(UTC).timestamp())
    payload = {"sub": "+919999999999", "exp": now + 3600}
    token = create_raw_token(payload)

    request = MagicMock(spec=Request)
    request.headers.get.return_value = f"Bearer {token}"

    subject = await require_authentication(request, settings=mock_settings)
    assert subject == "+919999999999"

@pytest.mark.asyncio
async def test_require_authentication_missing_header(mock_settings):
    """Test require_authentication dependency with missing Auth header."""
    request = MagicMock(spec=Request)
    request.headers.get.return_value = None

    with pytest.raises(UnauthorizedError) as exc:
        await require_authentication(request, settings=mock_settings)
    assert "Missing or invalid" in str(exc.value)

@pytest.mark.asyncio
async def test_require_authentication_invalid_scheme(mock_settings):
    """Test require_authentication dependency with non-Bearer auth scheme."""
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "Basic something"

    with pytest.raises(UnauthorizedError):
        await require_authentication(request, settings=mock_settings)

@pytest.mark.asyncio
async def test_require_authentication_invalid_subject(mock_settings):
    """Test require_authentication dependency with missing sub claim."""
    now = int(datetime.now(UTC).timestamp())
    payload = {"exp": now + 3600}
    token = create_raw_token(payload)

    request = MagicMock(spec=Request)
    request.headers.get.return_value = f"Bearer {token}"

    with pytest.raises(UnauthorizedError) as exc:
        await require_authentication(request, settings=mock_settings)
    assert "subject" in str(exc.value)
