"""Unit tests for JWT encode/decode helpers.

Tests ``_encode_jwt`` (in otp.py) and ``_decode_jwt`` (in security.py).
Both are pure stdlib HS256 implementations with no external dependencies.

All tests are pure in-process — no DB, no HTTP, no external services.
"""
from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from src.app.api.v1.endpoints.otp import _encode_jwt
from src.app.core.config import Settings
from src.app.core.exceptions import UnauthorizedError
from src.app.core.security import _decode_jwt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SECRET = "test-secret-key-that-is-at-least-32-characters"


def _make_settings(secret: str = SECRET) -> Settings:
    return Settings(
        SECRET_KEY=secret,
        ENVIRONMENT="development",
    )


def _make_payload(
    sub: str = "+919876543210",
    exp_delta_seconds: int = 300,
) -> dict:
    now = int(datetime.now(UTC).timestamp())
    return {
        "sub": sub,
        "iat": now,
        "exp": now + exp_delta_seconds,
        "role": "user",
    }


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


# ---------------------------------------------------------------------------
# _encode_jwt
# ---------------------------------------------------------------------------


class TestEncodeJwt:
    """Tests for the stdlib HS256 JWT encoder in otp.py."""

    def test_produces_three_segment_token(self):
        token = _encode_jwt(_make_payload(), secret=SECRET)
        parts = token.split(".")
        assert len(parts) == 3, "JWT must have exactly 3 dot-separated segments"

    def test_header_is_hs256(self):
        token = _encode_jwt(_make_payload(), secret=SECRET)
        header_b64 = token.split(".")[0]
        header = json.loads(_b64url_decode(header_b64))
        assert header["alg"] == "HS256"
        assert header["typ"] == "JWT"

    def test_payload_claims_round_trip(self):
        payload = _make_payload(sub="+919000000001")
        token = _encode_jwt(payload, secret=SECRET)
        payload_b64 = token.split(".")[1]
        decoded = json.loads(_b64url_decode(payload_b64))
        assert decoded["sub"] == "+919000000001"
        assert "exp" in decoded
        assert "iat" in decoded

    def test_different_secrets_produce_different_signatures(self):
        payload = _make_payload()
        t1 = _encode_jwt(payload, secret="secret-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        t2 = _encode_jwt(payload, secret="secret-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        sig1 = t1.split(".")[2]
        sig2 = t2.split(".")[2]
        assert sig1 != sig2

    def test_rejects_non_hs256_algorithm(self):
        with pytest.raises(ValueError, match="Only HS256"):
            _encode_jwt(_make_payload(), secret=SECRET, algorithm="RS256")


# ---------------------------------------------------------------------------
# _decode_jwt
# ---------------------------------------------------------------------------


class TestDecodeJwt:
    """Tests for the stdlib HS256 JWT decoder in security.py."""

    def test_valid_token_returns_payload(self):
        settings = _make_settings()
        payload = _make_payload()
        token = _encode_jwt(payload, secret=SECRET)
        decoded = _decode_jwt(token, settings=settings)
        assert decoded["sub"] == payload["sub"]

    def test_wrong_secret_raises_unauthorized(self):
        token = _encode_jwt(_make_payload(), secret=SECRET)
        wrong_settings = _make_settings(secret="wrong-secret-at-least-32-characters!!")
        with pytest.raises(UnauthorizedError, match="Invalid token signature"):
            _decode_jwt(token, settings=wrong_settings)

    def test_expired_token_raises_unauthorized(self):
        settings = _make_settings()
        payload = _make_payload(exp_delta_seconds=-1)  # already expired
        token = _encode_jwt(payload, secret=SECRET)
        with pytest.raises(UnauthorizedError, match="expired"):
            _decode_jwt(token, settings=settings)

    def test_malformed_token_missing_segments_raises(self):
        settings = _make_settings()
        with pytest.raises(UnauthorizedError, match="Invalid token format"):
            _decode_jwt("not.a.valid.jwt.token", settings=settings)

    def test_malformed_token_single_segment_raises(self):
        settings = _make_settings()
        with pytest.raises(UnauthorizedError, match="Invalid token format"):
            _decode_jwt("onlyone", settings=settings)

    def test_tampered_payload_raises(self):
        """Changing the payload must invalidate the signature."""
        settings = _make_settings()
        token = _encode_jwt(_make_payload(sub="+919876543210"), secret=SECRET)
        header, _, sig = token.split(".")
        # Build a new payload with an elevated role
        tampered_payload = _make_payload(sub="+919000000000")
        tampered_payload["role"] = "admin"
        tampered_json = json.dumps(tampered_payload, separators=(",", ":"), sort_keys=True).encode()
        tampered_b64 = base64.urlsafe_b64encode(tampered_json).rstrip(b"=").decode("ascii")
        tampered_token = f"{header}.{tampered_b64}.{sig}"
        with pytest.raises(UnauthorizedError, match="Invalid token signature"):
            _decode_jwt(tampered_token, settings=settings)

    def test_missing_exp_raises(self):
        settings = _make_settings()
        payload = {"sub": "+919876543210", "role": "user"}  # no exp
        token = _encode_jwt(payload, secret=SECRET)
        with pytest.raises(UnauthorizedError, match="Invalid token expiration"):
            _decode_jwt(token, settings=settings)

    def test_non_integer_exp_raises(self):
        settings = _make_settings()
        payload = {"sub": "+919876543210", "exp": "never"}
        token = _encode_jwt(payload, secret=SECRET)
        with pytest.raises(UnauthorizedError, match="Invalid token expiration"):
            _decode_jwt(token, settings=settings)


# ---------------------------------------------------------------------------
# Round-trip: encode → decode
# ---------------------------------------------------------------------------


class TestJwtRoundTrip:
    """Encode then decode must recover the original claims."""

    def test_full_round_trip(self):
        settings = _make_settings()
        payload = _make_payload(sub="+919999900000")
        token = _encode_jwt(payload, secret=SECRET)
        decoded = _decode_jwt(token, settings=settings)
        assert decoded["sub"] == "+919999900000"
        assert decoded["exp"] == payload["exp"]
        assert decoded["iat"] == payload["iat"]

    def test_round_trip_preserves_all_claims(self):
        settings = _make_settings()
        now = int(datetime.now(UTC).timestamp())
        payload = {
            "sub": "+919876543210",
            "iat": now,
            "exp": now + 3600,
            "doctor_id": 42,
            "role": "admin",
            "email": "dr@example.com",
        }
        token = _encode_jwt(payload, secret=SECRET)
        decoded = _decode_jwt(token, settings=settings)
        assert decoded["doctor_id"] == 42
        assert decoded["role"] == "admin"
        assert decoded["email"] == "dr@example.com"
