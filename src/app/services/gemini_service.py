"""
Gemini AI Service.

Production-grade wrapper for Google Gemini API using google-genai package.
Features:
- Automatic retries with exponential backoff
- Structured output parsing with JSON schema enforcement
- Comprehensive error handling
- Async/await for all I/O operations
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from google import genai
from google.genai import types as genai_types
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..core.config import get_settings
from ..core.exceptions import AIServiceError, ExtractionError

logger = logging.getLogger(__name__)

# Models with "live" in the id are for the Live/WebSocket API, not generateContent.
_LIVE_MODEL_MARKERS = ("-live", "live-preview")


def mask_api_key(api_key: str) -> str:
    """Return a log-safe API key fingerprint (first/last 4 chars)."""
    key = (api_key or "").strip()
    if not key:
        return "<not set>"
    if len(key) <= 8:
        return "<set>"
    return f"{key[:4]}...{key[-4:]}"


def gemini_remediation_hint(
    error_text: str,
    model: str,
    *,
    config_key: str = "GEMINI_MODEL",
) -> str:
    """Suggest a fix based on the Gemini API error message."""
    lowered = error_text.lower()

    if "resource_exhausted" in lowered or "429" in lowered:
        return (
            "Gemini API quota/billing exhausted for this key. "
            "Add credits in Google AI Studio or switch GOOGLE_API_KEY."
        )
    if (
        "api key expired" in lowered
        or "api_key_invalid" in lowered
        or "api key not valid" in lowered
        or "invalid api key" in lowered
    ):
        return "Update GOOGLE_API_KEY in backend .env and restart the server."
    if "not found" in lowered or "404" in lowered:
        if any(marker in model.lower() for marker in _LIVE_MODEL_MARKERS):
            return (
                f"Model '{model}' is a Live/voice model and does not support resume "
                f"extraction (generateContent). Set {config_key} to a generateContent "
                "model such as gemini-2.5-flash in .env."
            )
        return (
            f"Model '{model}' is unavailable or unsupported for generateContent. "
            f"Set {config_key} to a supported model (e.g. gemini-2.5-flash)."
        )
    if "not supported for generatecontent" in lowered:
        return (
            f"Model '{model}' cannot be used for resume parsing. "
            f"Use gemini-2.5-flash (or another generateContent model) in {config_key}."
        )
    return (
        f"Check server logs for the full Gemini error and verify "
        f"GOOGLE_API_KEY + {config_key}."
    )


class GeminiService:
    """
    Production-grade Google Gemini API wrapper using google-genai.

    Features:
    - Automatic retry with exponential backoff for transient failures
    - JSON schema enforcement for structured outputs
    - Request/response logging for debugging
    - Async support via the new SDK

    Usage:
        gemini = GeminiService()
        result = await gemini.generate_structured(
            prompt="Extract data from this text...",
        )
    """

    def __init__(self) -> None:
        """Initialize the Gemini client with API configuration."""
        self.settings = get_settings()
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        """Get or create the Gemini client instance."""
        if self._client is None:
            if not self.settings.GOOGLE_API_KEY:
                raise AIServiceError(
                    message="Google API key not configured",
                    original_error="GOOGLE_API_KEY environment variable is empty",
                )
            self._client = genai.Client(api_key=self.settings.GOOGLE_API_KEY)
            logger.info(
                "Initialized Gemini client model=%s api_key=%s",
                self.settings.GEMINI_MODEL,
                mask_api_key(self.settings.GOOGLE_API_KEY),
            )
        return self._client

    def _resolve_model(self, model: str | None) -> str:
        """Use explicit model override when provided, else default GEMINI_MODEL."""
        return model or self.settings.GEMINI_MODEL

    def _log_request_context(
        self,
        operation: str,
        *,
        model: str | None = None,
        mime_type: str | None = None,
        file_size_bytes: int | None = None,
        prompt_chars: int | None = None,
        config_key: str = "GEMINI_MODEL",
    ) -> None:
        """Log model + masked API key for every Gemini call."""
        resolved_model = self._resolve_model(model)
        logger.info(
            "Gemini %s: model=%s api_key=%s%s%s",
            operation,
            resolved_model,
            mask_api_key(self.settings.GOOGLE_API_KEY),
            f" mime_type={mime_type}" if mime_type else "",
            f" file_size_bytes={file_size_bytes}" if file_size_bytes is not None else "",
        )
        if prompt_chars is not None:
            logger.debug("Gemini %s prompt_chars=%d", operation, prompt_chars)
        if any(marker in resolved_model.lower() for marker in _LIVE_MODEL_MARKERS):
            logger.warning(
                "%s=%s looks like a Live/voice model; resume extraction "
                "requires a generateContent model (e.g. gemini-2.5-flash).",
                config_key,
                resolved_model,
            )

    def _raise_gemini_api_error(
        self,
        exc: Exception,
        operation: str,
        *,
        model: str | None = None,
        config_key: str = "GEMINI_MODEL",
    ) -> None:
        """Log full Gemini failure details and raise AIServiceError."""
        error_text = str(exc)
        resolved_model = self._resolve_model(model)
        remediation = gemini_remediation_hint(
            error_text, resolved_model, config_key=config_key
        )
        logger.error(
            "Gemini %s failed: model=%s api_key=%s error=%s remediation=%s",
            operation,
            resolved_model,
            mask_api_key(self.settings.GOOGLE_API_KEY),
            error_text,
            remediation,
            exc_info=True,
        )
        error_str = error_text.lower()
        if "blocked" in error_str or "safety" in error_str:
            raise AIServiceError(
                message="Request blocked by AI safety filters",
                original_error=error_text,
            ) from exc
        if (
            "api key expired" in error_str
            or "api_key_invalid" in error_str
            or "api key not valid" in error_str
            or "invalid api key" in error_str
        ):
            raise AIServiceError(
                message=(
                    "Google AI API key is invalid or expired. "
                    "Update GOOGLE_API_KEY in the backend .env and restart the server."
                ),
                original_error=error_text,
            ) from exc
        raise AIServiceError(
            message="AI service temporarily unavailable",
            original_error=error_text,
        ) from exc

    def _get_generation_config(
        self,
        temperature: float | None = None,
        max_tokens: int | None = None,
        *,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        """Create generation config with defaults from settings."""
        config: dict[str, Any] = {
            "temperature": temperature or self.settings.GEMINI_TEMPERATURE,
            "max_output_tokens": max_tokens or self.settings.GEMINI_MAX_TOKENS,
        }
        if json_mode:
            config["response_mime_type"] = "application/json"
        return config

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        """Collect text from a Gemini response (handles multi-part output)."""
        text = getattr(response, "text", None)
        if text:
            return text
        parts: list[str] = []
        for candidate in getattr(response, "candidates", None) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                part_text = getattr(part, "text", None)
                if part_text:
                    parts.append(part_text)
        return "".join(parts)

    @staticmethod
    def _response_finish_reason(response: Any) -> str | None:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        reason = getattr(candidates[0], "finish_reason", None)
        return str(reason) if reason is not None else None

    def _get_retry_decorator(self) -> Any:
        """Return a cached tenacity retry decorator.

        The decorator is built once and stored on the instance — rebuilding it
        on every ``generate_with_retry`` call wastes CPU and creates a new
        tenacity state machine each time, resetting retry statistics.
        """
        if not hasattr(self, "_retry_decorator"):
            self._retry_decorator = retry(
                stop=stop_after_attempt(self.settings.GEMINI_MAX_RETRIES),
                wait=wait_exponential(
                    multiplier=self.settings.GEMINI_RETRY_DELAY,
                    min=1,
                    max=60,
                ),
                retry=retry_if_exception_type((
                    ConnectionError,
                    TimeoutError,
                )),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=True,
            )
        return self._retry_decorator

    async def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        *,
        model: str | None = None,
        config_key: str = "GEMINI_MODEL",
        json_mode: bool = False,
    ) -> str:
        """
        Generate text response from Gemini.
        
        Args:
            prompt: The input prompt
            temperature: Override default temperature
            max_tokens: Override default max tokens
            
        Returns:
            Generated text response
            
        Raises:
            AIServiceError: If generation fails after retries
        """

        start_time = time.time()

        try:
            config = self._get_generation_config(
                temperature, max_tokens, json_mode=json_mode
            )

            resolved_model = self._resolve_model(model)
            self._log_request_context(
                "generate",
                model=resolved_model,
                prompt_chars=len(prompt),
                config_key=config_key,
            )

            # Use new google.genai API
            response = await self.client.aio.models.generate_content(
                model=resolved_model,
                contents=prompt,
                config=config,  # type: ignore[arg-type]
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info("Gemini generate response in %.2fms", elapsed_ms)

            return response.text or ""

        except AIServiceError:
            raise
        except Exception as e:
            self._raise_gemini_api_error(
                e, "generate", model=model, config_key=config_key
            )

    async def generate_with_retry(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        *,
        model: str | None = None,
        config_key: str = "GEMINI_MODEL",
        json_mode: bool = False,
    ) -> str:
        """
        Generate text with automatic retries.
        
        Uses exponential backoff for transient failures.
        """
        @self._get_retry_decorator()  # type: ignore[untyped-decorator]
        async def _generate() -> str:
            return await self.generate(
                prompt,
                temperature,
                max_tokens,
                model=model,
                config_key=config_key,
                json_mode=json_mode,
            )

        return await _generate()  # type: ignore[no-any-return]

    async def generate_structured(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        *,
        model: str | None = None,
        config_key: str = "GEMINI_MODEL",
        json_mode: bool = True,
    ) -> dict[str, Any]:
        """
        Generate structured JSON response from Gemini.
        
        Automatically parses the response as JSON and handles
        common formatting issues (markdown code blocks, etc.).
        
        Args:
            prompt: The input prompt (should request JSON output)
            temperature: Override default temperature
            max_tokens: Override default max tokens
            
        Returns:
            Parsed JSON as dictionary
            
        Raises:
            ExtractionError: If JSON parsing fails
            AIServiceError: If generation fails
        """
        raw_response = await self.generate_with_retry(
            prompt,
            temperature,
            max_tokens,
            model=model,
            config_key=config_key,
            json_mode=json_mode,
        )

        return self._parse_json_response(raw_response)

    def _parse_json_response(self, response: str) -> dict[str, Any]:
        """
        Parse JSON from Gemini response, handling common formatting issues.
        
        Gemini sometimes wraps JSON in markdown code blocks.
        """
        # Clean up response if wrapped in markdown
        cleaned = response.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]  # Remove ```json
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]  # Remove ```

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]  # Remove trailing ```

        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

        # Retry with strict=False — Gemini sometimes embeds literal newlines/control
        # characters inside string values, which are technically invalid JSON but
        # recoverable when strict mode is disabled.
        try:
            return json.loads(cleaned, strict=False)  # type: ignore[no-any-return]
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse JSON response: %s (response_chars=%d tail=%r)",
                e,
                len(cleaned),
                cleaned[-120:] if cleaned else "",
            )
            logger.debug("Raw response: %s", response)
            raise ExtractionError(
                message="Failed to parse AI response as JSON",
                source="gemini",
                details={
                    "parse_error": str(e),
                    "response_chars": len(cleaned),
                    "raw_response": response[:500],
                },
            )

    async def generate_with_vision(
        self,
        prompt: str,
        file_content: bytes,
        mime_type: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        *,
        model: str | None = None,
        config_key: str = "GEMINI_MODEL",
        json_mode: bool = True,
    ) -> dict[str, Any]:
        """
        Generate structured response from image/PDF using Gemini Vision.
        
        Args:
            prompt: Text prompt describing what to extract
            file_content: Raw bytes of the file
            mime_type: MIME type of the file
            temperature: Override default temperature
            max_tokens: Override default max tokens
            
        Returns:
            Parsed JSON response
            
        Raises:
            AIServiceError: If generation fails
            ExtractionError: If parsing fails
        """
        start_time = time.time()

        try:
            config = self._get_generation_config(
                temperature, max_tokens, json_mode=json_mode
            )

            # Create the Part for the new google.genai API
            image_part = genai_types.Part.from_bytes(
                data=file_content,
                mime_type=mime_type,
            )

            resolved_model = self._resolve_model(model)
            self._log_request_context(
                "vision",
                model=resolved_model,
                mime_type=mime_type,
                file_size_bytes=len(file_content),
                prompt_chars=len(prompt),
                config_key=config_key,
            )

            contents_list: list[Any] = [prompt, image_part]
            # Use new google.genai API with multimodal content
            response = await self.client.aio.models.generate_content(
                model=resolved_model,
                contents=contents_list,
                config=config,  # type: ignore[arg-type]
            )

            elapsed_ms = (time.time() - start_time) * 1000
            raw_text = self._extract_response_text(response)
            finish_reason = self._response_finish_reason(response)
            logger.info(
                "Gemini Vision response in %.2fms chars=%d finish_reason=%s",
                elapsed_ms,
                len(raw_text),
                finish_reason,
            )

            try:
                return self._parse_json_response(raw_text)
            except ExtractionError as parse_exc:
                if finish_reason == "MAX_TOKENS" or len(raw_text) < 1500:
                    logger.warning(
                        "Gemini vision JSON truncated (finish_reason=%s, chars=%d); "
                        "retrying with higher max_output_tokens",
                        finish_reason,
                        len(raw_text),
                    )
                    retry_tokens = (max_tokens or self.settings.GEMINI_MAX_TOKENS) * 2
                    retry_config = self._get_generation_config(
                        temperature,
                        retry_tokens,
                        json_mode=json_mode,
                    )
                    retry_response = await self.client.aio.models.generate_content(
                        model=resolved_model,
                        contents=contents_list,
                        config=retry_config,  # type: ignore[arg-type]
                    )
                    retry_text = self._extract_response_text(retry_response)
                    logger.info(
                        "Gemini Vision retry chars=%d finish_reason=%s",
                        len(retry_text),
                        self._response_finish_reason(retry_response),
                    )
                    return self._parse_json_response(retry_text)
                raise parse_exc

        except ExtractionError:
            raise
        except AIServiceError:
            raise
        except Exception as e:
            self._raise_gemini_api_error(
                e, "vision", model=model, config_key=config_key
            )


# Singleton instance for dependency injection
_gemini_service: GeminiService | None = None


def get_gemini_service() -> GeminiService:
    """Get the global Gemini service instance."""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
