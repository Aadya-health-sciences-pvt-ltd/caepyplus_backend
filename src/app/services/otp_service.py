"""OTP Authentication Service.

Handles OTP generation, storage (Redis with in-memory fallback),
SMS delivery via onlysms.co.in, and verification.
"""
import secrets
import time
from urllib.parse import quote

import httpx
import structlog

from ..core.config import get_settings

logger = structlog.get_logger(__name__)

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis package not installed — using in-memory OTP storage")


class RedisOTPStore:
    """Redis-backed OTP storage with automatic TTL and attempt tracking."""

    def __init__(
        self,
        redis_url: str,
        prefix: str = "otp:",
        ttl_seconds: int = 300,
        max_attempts: int = 3,
    ) -> None:
        self._redis_url = redis_url
        self._prefix = prefix
        self._ttl = ttl_seconds
        self._max_attempts = max_attempts
        self._redis: aioredis.Redis | None = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to Redis. Returns True on success."""
        if not REDIS_AVAILABLE:
            return False
        try:
            self._redis = aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()  # type: ignore[misc]
            self._connected = True
            logger.info("Redis OTP store connected", url=self._redis_url[:30] + "...")
            return True
        except Exception as exc:
            logger.warning("Redis connection failed — using in-memory fallback", error=str(exc))
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close the Redis connection."""
        if self._redis:
            await self._redis.close()
            self._connected = False

    def _otp_key(self, mobile: str) -> str:
        return f"{self._prefix}{mobile}"

    def _attempts_key(self, mobile: str) -> str:
        return f"{self._prefix}attempts:{mobile}"

    async def store_otp(self, mobile_number: str, otp: str) -> None:
        if not self._connected or not self._redis:
            raise ConnectionError("Redis not connected")
        await self._redis.setex(self._otp_key(mobile_number), self._ttl, otp)
        await self._redis.setex(self._attempts_key(mobile_number), self._ttl, "0")
        logger.debug("OTP stored in Redis", mobile=mobile_number[-4:], expires_in=self._ttl)

    async def verify_otp(self, mobile_number: str, otp: str) -> tuple[bool, str]:
        """Verify OTP. Returns (is_valid, message)."""
        if not self._connected or not self._redis:
            raise ConnectionError("Redis not connected")

        otp_key = self._otp_key(mobile_number)
        attempts_key = self._attempts_key(mobile_number)

        stored_otp = await self._redis.get(otp_key)
        if not stored_otp:
            return False, "OTP not found or expired. Please request a new OTP."

        attempts = int(await self._redis.get(attempts_key) or "0")
        if attempts >= self._max_attempts:
            await self._redis.delete(otp_key, attempts_key)
            return False, "Too many failed attempts. Please request a new OTP."

        if stored_otp != otp:
            await self._redis.incr(attempts_key)
            remaining = self._max_attempts - attempts - 1
            return False, f"Invalid OTP. {remaining} attempts remaining."

        await self._redis.delete(otp_key, attempts_key)
        return True, "OTP verified successfully"

    @property
    def is_connected(self) -> bool:
        return self._connected


class InMemoryOTPStore:
    """In-memory OTP storage — fallback when Redis is unavailable.

    WARNING: Not suitable for multi-process deployments. OTPs are
    lost on restart and not shared across workers.
    """

    def __init__(self, ttl_seconds: int = 300, max_attempts: int = 3) -> None:
        self._store: dict[str, tuple[str, float]] = {}
        self._attempts: dict[str, int] = {}
        self._ttl = ttl_seconds
        self._max_attempts = max_attempts

    async def store_otp(self, mobile_number: str, otp: str) -> None:
        self._store[mobile_number] = (otp, time.time() + self._ttl)
        self._attempts[mobile_number] = 0
        logger.debug("OTP stored in memory", mobile=mobile_number[-4:], expires_in=self._ttl)

    async def verify_otp(self, mobile_number: str, otp: str) -> tuple[bool, str]:
        """Verify OTP. Returns (is_valid, message)."""
        if mobile_number not in self._store:
            return False, "OTP not found. Please request a new OTP."

        stored_otp, expiry = self._store[mobile_number]
        if time.time() > expiry:
            del self._store[mobile_number]
            self._attempts.pop(mobile_number, None)
            return False, "OTP has expired. Please request a new OTP."

        attempts = self._attempts.get(mobile_number, 0)
        if attempts >= self._max_attempts:
            del self._store[mobile_number]
            self._attempts.pop(mobile_number, None)
            return False, "Too many failed attempts. Please request a new OTP."

        if stored_otp != otp:
            self._attempts[mobile_number] = attempts + 1
            remaining = self._max_attempts - attempts - 1
            return False, f"Invalid OTP. {remaining} attempts remaining."

        del self._store[mobile_number]
        self._attempts.pop(mobile_number, None)
        return True, "OTP verified successfully"

    def cleanup_expired(self) -> int:
        """Remove all expired OTP entries.

        Returns the number of entries removed.  Useful for tests and
        periodic maintenance in long-running processes.
        """
        now = time.time()
        expired = [mobile for mobile, (_, expiry) in self._store.items() if now > expiry]
        for mobile in expired:
            del self._store[mobile]
            self._attempts.pop(mobile, None)
        return len(expired)


class OTPService:
    """OTP authentication service.

    Uses Redis for OTP storage with automatic in-memory fallback.
    SMS is delivered via the onlysms.co.in API.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._redis_store: RedisOTPStore | None = None
        self._memory_store: InMemoryOTPStore | None = None
        self._initialized = False
        self.http_client = httpx.AsyncClient(timeout=30.0, verify=False, trust_env=False)

    async def _init_store(self) -> None:
        """Initialize the OTP store (Redis first, memory fallback)."""
        if self._initialized:
            return

        if self.settings.REDIS_ENABLED and REDIS_AVAILABLE:
            self._redis_store = RedisOTPStore(
                redis_url=self.settings.REDIS_URL,
                prefix=self.settings.REDIS_OTP_PREFIX,
                ttl_seconds=self.settings.OTP_EXPIRY_SECONDS,
                max_attempts=self.settings.OTP_MAX_ATTEMPTS,
            )
            if await self._redis_store.connect():
                logger.info("Using Redis for OTP storage")
                self._initialized = True
                return

        logger.info("Using in-memory OTP storage (Redis unavailable or disabled)")
        self._memory_store = InMemoryOTPStore(
            ttl_seconds=self.settings.OTP_EXPIRY_SECONDS,
            max_attempts=self.settings.OTP_MAX_ATTEMPTS,
        )
        self._initialized = True

    async def _get_store(self) -> RedisOTPStore | InMemoryOTPStore:
        await self._init_store()
        if self._redis_store and self._redis_store.is_connected:
            return self._redis_store
        return self._memory_store  # type: ignore[return-value]

    def generate_otp(self, length: int = 6) -> str:
        """Generate a cryptographically secure numeric OTP."""
        return "".join(secrets.choice("0123456789") for _ in range(length))

    def mask_mobile(self, mobile_number: str) -> str:
        """Return a masked version of the mobile number for safe logging."""
        if len(mobile_number) >= 10:
            return f"{mobile_number[:2]}****{mobile_number[-4:]}"
        return "****"

    async def send_otp(self, mobile_number: str, delivery_method: str = "sms") -> tuple[bool, str]:
        """Generate and send an OTP via SMS or WhatsApp.

        Returns:
            (True, success_message) on success, (False, error_message) on failure.
        """
        # ------------------------------------------------------------------
        # SKIP_VERIFY bypass — development / testing mode only
        # ------------------------------------------------------------------
        if self.settings.SKIP_VERIFY:
            logger.warning(
                "SKIP_VERIFY is enabled — OTP sending bypassed (dev/test mode only)",
                mobile=self.mask_mobile(mobile_number),
                delivery_method=delivery_method,
            )
            return True, "OTP bypassed (SKIP_VERIFY mode). Use any OTP to verify."

        try:
            store = await self._get_store()
            otp = self.generate_otp(length=self.settings.OTP_LENGTH)
            
            if delivery_method.lower() == "whatsapp":
                logger.info(
                    "Sending OTP via WhatsApp",
                    mobile=self.mask_mobile(mobile_number),
                    storage_type="redis" if isinstance(store, RedisOTPStore) else "memory",
                )
                
                payload = {
                    "communication_type": "whatsapp",
                    "message_type": "template",
                    "to": mobile_number,
                    "template_name": "otp_linqmd",
                    "template_params": {
                        "components": [
                            {
                                "type": "body",
                                "parameters": [
                                    {
                                        "type": "text",
                                        "text": otp
                                    }
                                ]
                            },
                            {
                                "type": "button",
                                "sub_type": "url",
                                "index": "0",
                                "parameters": [
                                    {
                                        "type": "payload",
                                        "payload": otp
                                    }
                                ]
                            }
                        ]
                    }
                }
                
                response = await self.http_client.post(
                    self.settings.LINQMD_COMMUNICATION_SERVICE_URL,
                    json=payload
                )
                
                # Log the raw response from communication service
                logger.info("WhatsApp API response", status_code=response.status_code, body=response.text[:200])
                
                response_data = response.json()
                
                if response.status_code != 201 or response_data.get("status_code") != 201:
                    logger.error("WhatsApp API error", status_code=response.status_code, response=response_data)
                    return False, "Failed to send OTP via WhatsApp. Please try again."
                
                # Parse the success response format
                response_message = response_data.get("message", "OTP sent successfully via WhatsApp")
                message_id = response_data.get("data", {}).get("message_id")
                
                await store.store_otp(mobile_number, otp)
                
                logger.info("OTP sent successfully via WhatsApp", 
                            mobile=self.mask_mobile(mobile_number),
                            message_id=message_id)
                return True, response_message

            # SMS delivery flow
            if not self.settings.SMS_USER_ID or not self.settings.SMS_USER_PASS:
                logger.error("SMS credentials missing")
                return False, "SMS service configuration error. Please check environment variables."

            try:
                sms_message = self.settings.SMS_OTP_MESSAGE_TEMPLATE.format(otp=otp)
            except Exception as exc:
                logger.error("Failed to format SMS_OTP_MESSAGE_TEMPLATE", error=str(exc))
                sms_message = self.settings.SMS_OTP_MESSAGE_TEMPLATE

            sms_url = (
                f"{self.settings.SMS_API_BASE_URL}"
                f"?UserID={self.settings.SMS_USER_ID}"
                f"&UserPass={self.settings.SMS_USER_PASS}"
                f"&MobileNo={mobile_number}"
                f"&GSMID={self.settings.SMS_GSM_ID}"
                f"&PEID={self.settings.SMS_PE_ID}"
                f"&Message={quote(sms_message)}"
                f"&TEMPID={self.settings.SMS_TEMPLATE_ID}"
                f"&UNICODE=TEXT"
            )

            logger.info(
                "Sending OTP via SMS",
                mobile=self.mask_mobile(mobile_number),
                storage_type="redis" if isinstance(store, RedisOTPStore) else "memory",
            )

            response = await self.http_client.get(sms_url)
            response_text = response.text
            logger.info("SMS API response", status_code=response.status_code, body=response_text[:200])

            if response.status_code != 200:
                logger.error("SMS API HTTP error", status_code=response.status_code)
                return False, "Failed to send OTP. Please try again."

            # onlysms.co.in success format: "100=<transaction_id>"
            if not response_text.startswith("100="):
                logger.error("SMS API returned non-success response", response=response_text)
                return False, f"SMS API error: {response_text[:100]}"

            await store.store_otp(mobile_number, otp)
            logger.info("OTP sent successfully via SMS", mobile=self.mask_mobile(mobile_number))
            return True, "OTP sent successfully"

        except httpx.TimeoutException:
            logger.error("SMS API timeout")
            return False, "SMS service timeout. Please try again."
        except Exception as exc:
            # Do NOT pass exc_info=True here — httpx exceptions embed the full
            # request URL (including UserID/UserPass query params) in the
            # traceback, which would leak SMS credentials into log aggregators.
            logger.error("OTP send error", error=type(exc).__name__)
            return False, "Failed to send OTP. Please try again."

    async def verify_otp(self, mobile_number: str, otp: str) -> tuple[bool, str]:
        """Verify the OTP for a given mobile number."""
        store = await self._get_store()
        return await store.verify_otp(mobile_number, otp)

    async def close(self) -> None:
        """Close HTTP client and Redis connections."""
        await self.http_client.aclose()
        if self._redis_store:
            await self._redis_store.disconnect()


# ---------------------------------------------------------------------------
# Process-level singleton
# ---------------------------------------------------------------------------

_otp_service: OTPService | None = None


def get_otp_service() -> OTPService:
    """Return the process-level OTPService singleton.

    Intentionally synchronous: this function only reads/writes a module-level
    variable and instantiates OTPService.  The lazy-init of the internal store
    (Redis connection, etc.) is deferred to the first ``send_otp`` /
    ``verify_otp`` call.  FastAPI resolves sync and async ``Depends`` callables
    identically, so callers do not need to change.
    """
    global _otp_service
    if _otp_service is None:
        _otp_service = OTPService()
    return _otp_service
