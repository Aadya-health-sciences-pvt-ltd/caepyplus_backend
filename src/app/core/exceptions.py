"""
Custom Exception Classes.

Provides a hierarchy of domain-specific exceptions that are automatically
converted to appropriate HTTP responses by the global exception handler.
"""

from typing import Any


class AppException(Exception):
    """
    Base exception for all application-specific errors.
    
    All custom exceptions should inherit from this class.
    The global exception handler converts these to HTTP responses.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "APP_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for JSON response."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }

# ============================================
# 4xx Client Errors
# ============================================

class BadRequestError(AppException):
    """Invalid request data or parameters (400)."""

    def __init__(
        self,
        message: str = "Invalid request",
        error_code: str = "BAD_REQUEST",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=400,
            details=details,
        )

class UnauthorizedError(AppException):
    """Authentication required or failed (401)."""

    def __init__(
        self,
        message: str = "Authentication required",
        error_code: str = "UNAUTHORIZED",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=401,
            details=details,
        )

class ForbiddenError(AppException):
    """Permission denied (403)."""

    def __init__(
        self,
        message: str = "Permission denied",
        error_code: str = "FORBIDDEN",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=403,
            details=details,
        )

class NotFoundError(AppException):
    """Resource not found (404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        error_code: str = "NOT_FOUND",
        resource_type: str | None = None,
        resource_id: str | int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=404,
            details=details,
        )

class ConflictError(AppException):
    """Resource conflict, e.g., duplicate entry (409)."""

    def __init__(
        self,
        message: str = "Resource conflict",
        error_code: str = "CONFLICT",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=409,
            details=details,
        )

class ValidationError(AppException):
    """Data validation failed (422)."""

    def __init__(
        self,
        message: str = "Validation failed",
        error_code: str = "VALIDATION_ERROR",
        errors: list[dict[str, Any]] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if errors:
            details["validation_errors"] = errors
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=422,
            details=details,
        )

class RateLimitError(AppException):
    """Rate limit exceeded (429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        error_code: str = "RATE_LIMIT_EXCEEDED",
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=429,
            details=details,
        )

# ============================================
# 5xx Server Errors
# ============================================

class InternalServerError(AppException):
    """Internal server error (500)."""

    def __init__(
        self,
        message: str = "Internal server error",
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=500,
            details=details,
        )

class ServiceUnavailableError(AppException):
    """Service temporarily unavailable (503)."""

    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        error_code: str = "SERVICE_UNAVAILABLE",
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=503,
            details=details,
        )

class ExternalServiceError(AppException):
    """External service call failed (502)."""

    def __init__(
        self,
        service_name: str,
        message: str | None = None,
        error_code: str = "EXTERNAL_SERVICE_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        details["service"] = service_name
        super().__init__(
            message=message or f"External service '{service_name}' is unavailable or returned an error",
            error_code=error_code,
            status_code=502,
            details=details,
        )

# ============================================
# Domain-Specific Exceptions
# ============================================

class DoctorNotFoundError(NotFoundError):
    """Doctor resource not found."""

    def __init__(
        self,
        doctor_id: int | None = None,
        email: str | None = None,
        message: str | None = None,
    ) -> None:
        identifier = doctor_id or email
        super().__init__(
            message=message or f"Doctor not found: {identifier}",
            error_code="DOCTOR_NOT_FOUND",
            resource_type="doctor",
            resource_id=identifier,
        )

class DoctorAlreadyExistsError(ConflictError):
    """Doctor with same email already exists."""

    def __init__(self, email: str | None = None, phone_number: str | None = None) -> None:
        details: dict[str, Any] = {}

        if email:
            details["email"] = email
        if phone_number:
            details["phone_number"] = phone_number

        if email and phone_number:
            message = f"Doctor with email '{email}' or phone number '{phone_number}' already exists"
        elif phone_number:
            message = f"Doctor with phone number '{phone_number}' already exists"
        else:
            # Backward-compatible default
            message = f"Doctor with email '{email}' already exists"

        super().__init__(
            message=message,
            error_code="DOCTOR_ALREADY_EXISTS",
            details=details,
        )

class OnboardingProfileAlreadyExistsError(ConflictError):
    """Onboarding profile with same email or phone already exists."""

    def __init__(self, email: str | None = None, phone_number: str | None = None) -> None:
        details: dict[str, Any] = {}

        if email:
            details["email"] = email
        if phone_number:
            details["phone_number"] = phone_number

        if email and phone_number:
            message = (
                f"Onboarding profile with email '{email}' or phone number "
                f"'{phone_number}' already exists"
            )
        elif phone_number:
            message = f"Onboarding profile with phone number '{phone_number}' already exists"
        else:
            message = f"Onboarding profile with email '{email}' already exists"

        super().__init__(
            message=message,
            error_code="PROFILE_ALREADY_EXISTS",
            details=details,
        )

class SessionNotFoundError(NotFoundError):
    """Voice session not found."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            message=f"Voice session not found: {session_id}",
            error_code="SESSION_NOT_FOUND",
            resource_type="voice_session",
            resource_id=session_id,
        )

class SessionExpiredError(BadRequestError):
    """Voice session has expired."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            message=f"Voice session has expired: {session_id}",
            error_code="SESSION_EXPIRED",
            details={"session_id": session_id},
        )

class ConfigurationError(AppException):
    """Application configuration error."""

    def __init__(
        self,
        message: str = "Configuration error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            status_code=500,
            details=details,
        )

class FileValidationError(BadRequestError):
    """File upload validation failed."""

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        allowed_types: list[str] | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if filename:
            details["filename"] = filename
        if allowed_types:
            details["allowed_types"] = allowed_types
        super().__init__(
            message=message,
            error_code="FILE_VALIDATION_ERROR",
            details=details,
        )

class AIServiceError(ServiceUnavailableError):
    """AI/Gemini service error."""

    def __init__(
        self,
        message: str = "AI service temporarily unavailable",
        original_error: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if original_error:
            details["original_error"] = original_error
        super().__init__(
            message=message,
            error_code="AI_SERVICE_ERROR",
            retry_after=60,
            details=details,
        )

class ExtractionError(AppException):
    """Data extraction from resume/voice failed."""

    def __init__(
        self,
        message: str = "Failed to extract data",
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if source:
            details["source"] = source
        super().__init__(
            message=message,
            error_code="EXTRACTION_ERROR",
            status_code=422,
            details=details,
        )
