"""Tests for custom exceptions in core.exceptions."""

from src.app.core.exceptions import (
    AIServiceError,
    AppException,
    BadRequestError,
    ConfigurationError,
    ConflictError,
    DoctorAlreadyExistsError,
    DoctorNotFoundError,
    ExternalServiceError,
    ExtractionError,
    FileValidationError,
    ForbiddenError,
    InternalServerError,
    NotFoundError,
    OnboardingProfileAlreadyExistsError,
    RateLimitError,
    ServiceUnavailableError,
    SessionExpiredError,
    SessionNotFoundError,
    UnauthorizedError,
    ValidationError,
)


def test_app_exception_to_dict():
    """Test the to_dict method serialization."""
    exc = AppException("Test message", "TEST_CODE", 400, {"key": "value"})
    data = exc.to_dict()
    assert data["error"]["code"] == "TEST_CODE"
    assert data["error"]["message"] == "Test message"
    assert data["error"]["details"]["key"] == "value"
    assert exc.status_code == 400

def test_http_error_instantiation():
    """Test standard HTTP exception instantiations."""
    assert BadRequestError().status_code == 400
    assert UnauthorizedError().status_code == 401
    assert ForbiddenError().status_code == 403

    not_found = NotFoundError(resource_type="user", resource_id=1)
    assert not_found.status_code == 404
    assert not_found.details["resource_type"] == "user"
    assert not_found.details["resource_id"] == 1

    assert ConflictError().status_code == 409

    validation = ValidationError(errors=[{"msg": "bad"}])
    assert validation.status_code == 422
    assert "validation_errors" in validation.details

    rate = RateLimitError(retry_after=60)
    assert rate.status_code == 429
    assert rate.details["retry_after_seconds"] == 60

    assert InternalServerError().status_code == 500

    svc_unavail = ServiceUnavailableError(retry_after=120)
    assert svc_unavail.status_code == 503
    assert svc_unavail.details["retry_after_seconds"] == 120

    ext_err = ExternalServiceError("payment_gateway")
    assert ext_err.status_code == 502
    assert ext_err.details["service"] == "payment_gateway"

def test_domain_error_instantiation():
    """Test domain-specific exception instantiations."""
    doc_not_found = DoctorNotFoundError(doctor_id=123)
    assert doc_not_found.status_code == 404
    assert doc_not_found.details["resource_type"] == "doctor"
    assert doc_not_found.details["resource_id"] == 123

    doc_exists = DoctorAlreadyExistsError(email="test@example.com")
    assert doc_exists.status_code == 409

    profile_exists = OnboardingProfileAlreadyExistsError(phone_number="+1234567890")
    assert profile_exists.status_code == 409

    session_not_found = SessionNotFoundError("sess-1")
    assert session_not_found.status_code == 404
    assert session_not_found.details["resource_id"] == "sess-1"

    session_expired = SessionExpiredError("sess-2")
    assert session_expired.status_code == 400
    assert session_expired.details["session_id"] == "sess-2"

    assert ConfigurationError().status_code == 500

    file_err = FileValidationError("Bad extension", filename="test.exe", allowed_types=[".pdf"])
    assert file_err.status_code == 400
    assert file_err.details["filename"] == "test.exe"

    ai_err = AIServiceError(original_error="timeout")
    assert ai_err.status_code == 503
    assert ai_err.details["retry_after_seconds"] == 60
    assert ai_err.details["original_error"] == "timeout"

    extract_err = ExtractionError(source="resume")
    assert extract_err.status_code == 422
    assert extract_err.details["source"] == "resume"

def test_doctor_already_exists_messages():
    """Test message formatting based on arguments."""
    exc1 = DoctorAlreadyExistsError(email="test@test.com", phone_number="123")
    assert "email 'test@test.com' or phone number '123'" in exc1.message

    exc2 = DoctorAlreadyExistsError(phone_number="123")
    assert "phone number '123'" in exc2.message

    exc3 = DoctorAlreadyExistsError(email="test@test.com")
    assert "email 'test@test.com'" in exc3.message

def test_onboarding_profile_already_exists_messages():
    """Test message formatting based on arguments."""
    exc1 = OnboardingProfileAlreadyExistsError(email="test@test.com", phone_number="123")
    assert "email 'test@test.com' or phone number '123'" in exc1.message

    exc2 = OnboardingProfileAlreadyExistsError(phone_number="123")
    assert "phone number '123'" in exc2.message

    exc3 = OnboardingProfileAlreadyExistsError(email="test@test.com")
    assert "email 'test@test.com'" in exc3.message
