"""Unit tests for authentication schema validators.

Covers ``_normalise_indian_mobile`` (extracted module-level helper) through
both the bare function and its Pydantic-wired entry points in
``OTPRequestSchema`` and ``OTPVerifySchema``.

All tests run entirely in-process — no DB, no HTTP, no external services.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.app.schemas.auth import (
    OTPRequestSchema,
    OTPVerifySchema,
    _normalise_indian_mobile,
)


# ---------------------------------------------------------------------------
# _normalise_indian_mobile — bare function
# ---------------------------------------------------------------------------


class TestNormaliseIndianMobile:
    """Direct unit tests for the normalisation helper."""

    # -- happy path ----------------------------------------------------------

    def test_plain_10_digit(self):
        assert _normalise_indian_mobile("9876543210") == "9876543210"

    def test_starting_6(self):
        assert _normalise_indian_mobile("6123456789") == "6123456789"

    def test_starting_7(self):
        assert _normalise_indian_mobile("7000000001") == "7000000001"

    def test_starting_8(self):
        assert _normalise_indian_mobile("8888888888") == "8888888888"

    def test_strip_plus91_prefix(self):
        assert _normalise_indian_mobile("+919876543210") == "9876543210"

    def test_strip_91_prefix_12_digits(self):
        assert _normalise_indian_mobile("919876543210") == "9876543210"

    def test_strip_spaces(self):
        assert _normalise_indian_mobile("98765 43210") == "9876543210"

    def test_strip_dashes(self):
        assert _normalise_indian_mobile("98765-43210") == "9876543210"

    def test_strip_spaces_and_dashes(self):
        assert _normalise_indian_mobile("+91 98765-43210") == "9876543210"

    # -- rejection -----------------------------------------------------------

    def test_rejects_9_digits(self):
        with pytest.raises(ValueError, match="Invalid mobile number"):
            _normalise_indian_mobile("987654321")

    def test_rejects_11_digits_no_prefix(self):
        with pytest.raises(ValueError, match="Invalid mobile number"):
            _normalise_indian_mobile("98765432100")

    def test_rejects_starting_with_5(self):
        with pytest.raises(ValueError, match="Invalid mobile number"):
            _normalise_indian_mobile("5123456789")

    def test_rejects_starting_with_0(self):
        with pytest.raises(ValueError, match="Invalid mobile number"):
            _normalise_indian_mobile("0123456789")

    def test_rejects_letters(self):
        with pytest.raises(ValueError, match="Invalid mobile number"):
            _normalise_indian_mobile("9ABCDEFGHI")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="Invalid mobile number"):
            _normalise_indian_mobile("")


# ---------------------------------------------------------------------------
# OTPRequestSchema — wired through Pydantic
# ---------------------------------------------------------------------------


class TestOTPRequestSchema:
    """Validate that OTPRequestSchema.mobile_number delegates correctly."""

    def test_valid_number_accepted(self):
        obj = OTPRequestSchema(mobile_number="9876543210")
        assert obj.mobile_number == "9876543210"

    def test_plus91_prefix_stripped(self):
        obj = OTPRequestSchema(mobile_number="+919876543210")
        assert obj.mobile_number == "9876543210"

    def test_invalid_number_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            OTPRequestSchema(mobile_number="123456789")
        errors = exc_info.value.errors()
        assert any("mobile_number" in str(e["loc"]) for e in errors)

    def test_invalid_starting_digit_raises(self):
        with pytest.raises(ValidationError):
            OTPRequestSchema(mobile_number="5000000000")


# ---------------------------------------------------------------------------
# OTPVerifySchema — same validator applied to the same field
# ---------------------------------------------------------------------------


class TestOTPVerifySchema:
    """Validate that OTPVerifySchema uses the same normalisation logic."""

    def test_valid_number_and_otp(self):
        obj = OTPVerifySchema(mobile_number="9876543210", otp="123456")
        assert obj.mobile_number == "9876543210"
        assert obj.otp == "123456"

    def test_plus91_stripped(self):
        obj = OTPVerifySchema(mobile_number="+919876543210", otp="000000")
        assert obj.mobile_number == "9876543210"

    def test_invalid_number_raises(self):
        with pytest.raises(ValidationError):
            OTPVerifySchema(mobile_number="4999999999", otp="123456")
