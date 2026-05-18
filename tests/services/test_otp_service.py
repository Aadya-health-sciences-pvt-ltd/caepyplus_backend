"""Unit tests for OTP Service."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.app.services.otp_service import InMemoryOTPStore, OTPService, RedisOTPStore

# --- InMemoryOTPStore Tests ---

@pytest.mark.asyncio
async def test_in_memory_store_success():
    store = InMemoryOTPStore(ttl_seconds=300, max_attempts=3)
    await store.store_otp("1234567890", "123456")

    # Valid OTP
    success, msg = await store.verify_otp("1234567890", "123456")
    assert success is True
    assert "successfully" in msg

@pytest.mark.asyncio
async def test_in_memory_store_invalid_otp():
    store = InMemoryOTPStore(ttl_seconds=300, max_attempts=3)
    await store.store_otp("1234567890", "123456")

    # Invalid OTP
    success, msg = await store.verify_otp("1234567890", "000000")
    assert success is False
    assert "Invalid" in msg
    assert "attempts remaining" in msg

@pytest.mark.asyncio
async def test_in_memory_store_max_attempts():
    store = InMemoryOTPStore(ttl_seconds=300, max_attempts=2)
    await store.store_otp("1234567890", "123456")

    await store.verify_otp("1234567890", "000000") # Attempt 1
    await store.verify_otp("1234567890", "000000") # Attempt 2

    success, msg = await store.verify_otp("1234567890", "123456") # Attempt 3
    assert success is False
    assert "Too many failed attempts" in msg

    # Check if removed
    success, _ = await store.verify_otp("1234567890", "123456")
    assert success is False

@pytest.mark.asyncio
async def test_in_memory_store_expired():
    store = InMemoryOTPStore(ttl_seconds=-1, max_attempts=3)
    await store.store_otp("1234567890", "123456")

    success, msg = await store.verify_otp("1234567890", "123456")
    assert success is False
    assert "expired" in msg

def test_in_memory_store_cleanup():
    store = InMemoryOTPStore(ttl_seconds=-1, max_attempts=3)
    store._store["1234567890"] = ("123456", time.time() - 10)

    count = store.cleanup_expired()
    assert count == 1
    assert "1234567890" not in store._store

# --- RedisOTPStore Tests ---

@pytest.mark.asyncio
async def test_redis_store_success():
    redis_mock = AsyncMock()
    redis_mock.get.side_effect = ["123456", "0"]

    store = RedisOTPStore("redis://localhost")
    store._redis = redis_mock
    store._connected = True

    success, msg = await store.verify_otp("1234567890", "123456")
    assert success is True
    assert "successfully" in msg

@pytest.mark.asyncio
async def test_redis_store_invalid_otp():
    redis_mock = AsyncMock()
    redis_mock.get.side_effect = ["123456", "0"]

    store = RedisOTPStore("redis://localhost")
    store._redis = redis_mock
    store._connected = True

    success, msg = await store.verify_otp("1234567890", "000000")
    assert success is False
    assert "Invalid" in msg

@pytest.mark.asyncio
async def test_redis_store_max_attempts():
    redis_mock = AsyncMock()
    redis_mock.get.side_effect = ["123456", "3"] # Max attempts reached

    store = RedisOTPStore("redis://localhost", max_attempts=3)
    store._redis = redis_mock
    store._connected = True

    success, msg = await store.verify_otp("1234567890", "000000")
    assert success is False
    assert "Too many failed attempts" in msg

# --- OTPService Tests ---

@pytest.fixture
def otp_service():
    service = OTPService()
    service.settings.SMS_USER_ID = "test_user"
    service.settings.SMS_USER_PASS = "test_pass"
    service.settings.SMS_OTP_MESSAGE_TEMPLATE = "Your OTP is {otp}"
    service.settings.REDIS_ENABLED = False
    service._memory_store = InMemoryOTPStore()
    service._initialized = True
    return service

@pytest.mark.asyncio
async def test_send_otp_success(otp_service):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "100=SuccessMsg"
        mock_get.return_value = mock_response

        success, msg = await otp_service.send_otp("1234567890")
        assert success is True
        assert "successfully" in msg
        mock_get.assert_called_once()

        # Verify it was stored
        assert "1234567890" in otp_service._memory_store._store

@pytest.mark.asyncio
async def test_send_otp_api_failure(otp_service):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ERROR=Invalid Credentials"
        mock_get.return_value = mock_response

        success, msg = await otp_service.send_otp("1234567890")
        assert success is False
        assert "SMS API error" in msg

@pytest.mark.asyncio
async def test_send_otp_missing_credentials(otp_service):
    otp_service.settings.SMS_USER_ID = ""
    success, msg = await otp_service.send_otp("1234567890")
    assert success is False
    assert "configuration error" in msg

@pytest.mark.asyncio
async def test_send_otp_timeout(otp_service):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Timeout")

        success, msg = await otp_service.send_otp("1234567890")
        assert success is False
        assert "timeout" in msg
