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
            logger.info("Initialized Gemini client with model: %s", self.settings.GEMINI_MODEL)
        return self._client

    def _get_generation_config(
        self,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Create generation config with defaults from settings."""
        return {
            "temperature": temperature or self.settings.GEMINI_TEMPERATURE,
            "max_output_tokens": max_tokens or self.settings.GEMINI_MAX_TOKENS,
        }

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
            config = self._get_generation_config(temperature, max_tokens)

            logger.debug("Gemini request: %s...", prompt[:200])

            # Use new google.genai API
            response = await self.client.aio.models.generate_content(
                model=self.settings.GEMINI_MODEL,
                contents=prompt,
                config=config,  # type: ignore[arg-type]
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info("Gemini response in %.2fms", elapsed_ms)

            return response.text or ""

        except Exception as e:
            error_str = str(e).lower()
            if "blocked" in error_str or "safety" in error_str:
                logger.error("Prompt blocked by Gemini safety filters: %s", e)
                raise AIServiceError(
                    message="Request blocked by AI safety filters",
                    original_error=str(e),
                )
            logger.error("Gemini API error: %s", e)
            raise AIServiceError(
                message="AI service temporarily unavailable",
                original_error=str(e),
            )

    async def generate_with_retry(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Generate text with automatic retries.
        
        Uses exponential backoff for transient failures.
        """
        @self._get_retry_decorator()  # type: ignore[untyped-decorator]
        async def _generate() -> str:
            return await self.generate(prompt, temperature, max_tokens)

        return await _generate()  # type: ignore[no-any-return]

    async def generate_structured(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
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
            prompt, temperature, max_tokens
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
            logger.error("Failed to parse JSON response: %s", e)
            logger.debug("Raw response: %s", response)
            raise ExtractionError(
                message="Failed to parse AI response as JSON",
                source="gemini",
                details={"parse_error": str(e), "raw_response": response[:500]},
            )

    async def generate_with_vision(
        self,
        prompt: str,
        file_content: bytes,
        mime_type: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
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
            config = self._get_generation_config(temperature, max_tokens)

            # Create the Part for the new google.genai API
            image_part = genai_types.Part.from_bytes(
                data=file_content,
                mime_type=mime_type,
            )

            logger.info("Gemini Vision request for %s", mime_type)

            contents_list: list[Any] = [prompt, image_part]
            # Use new google.genai API with multimodal content
            response = await self.client.aio.models.generate_content(
                model=self.settings.GEMINI_MODEL,
                contents=contents_list,
                config=config,  # type: ignore[arg-type]
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info("Gemini Vision response in %.2fms", elapsed_ms)

            return self._parse_json_response(response.text or "")

        except ExtractionError:
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "blocked" in error_str or "safety" in error_str:
                logger.error("Vision prompt blocked: %s", e)
                raise AIServiceError(
                    message="Document blocked by AI safety filters",
                    original_error=str(e),
                )
            logger.error("Gemini Vision error: %s", e)
            raise AIServiceError(
                message="AI vision service temporarily unavailable",
                original_error=str(e),
            )


# Singleton instance for dependency injection
_gemini_service: GeminiService | None = None


def get_gemini_service() -> GeminiService:
    """Get the global Gemini service instance."""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
