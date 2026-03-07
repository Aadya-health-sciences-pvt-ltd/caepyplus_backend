"""
Onboarding Endpoints.

Unified onboarding API for resume extraction and profile verification.
Demonstrates the clean architecture with service layer abstraction.
"""
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from ....core.config import Settings, get_settings
from ....core.exceptions import FileValidationError
from ....core.rbac import AdminOrOperationUser, CurrentUser
from ....core.responses import GenericResponse
from ....db.session import DbSession
from ....models.enums import UserRole
from ....models.onboarding import OnboardingStatus
from ....repositories.doctor_repository import DoctorRepository
from ....repositories.onboarding_repository import OnboardingRepository
from ....schemas.doctor import ExtractionResponse
from ....services.email_service import EmailService, get_email_service
from ....services.extraction_service import get_extraction_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/onboarding")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _doctor_template_vars(
    doctor: Any,
    email_svc: EmailService,
    reason: str = "",
) -> dict[str, str]:
    """Build the standard email template variable dict from a Doctor ORM row."""
    return email_svc.build_template_vars(
        doctor_name=getattr(doctor, "full_name", None) or doctor.email or "",
        first_name="",
        medical_registration_number=getattr(doctor, "medical_registration_number", "") or "",
        medical_council=getattr(doctor, "medical_council", "") or "",
        specialization=getattr(doctor, "primary_specialization", "") or "",
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def validate_file(
    file: UploadFile,
    settings: Settings,
) -> None:
    """
    Validate uploaded file type and size.

    Raises:
        FileValidationError: If validation fails
    """
    if not file.filename:
        raise FileValidationError(
            message="Filename is required",
        )

    # Check extension
    extension = file.filename.lower().rsplit(".", 1)[-1]
    if extension not in settings.allowed_extensions_list:
        raise FileValidationError(
            message=f"Invalid file type: {extension}",
            filename=file.filename,
            allowed_types=settings.allowed_extensions_list,
        )

    # Check content type
    valid_content_types = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
    ]
    if file.content_type and file.content_type not in valid_content_types:
        raise FileValidationError(
            message=f"Invalid content type: {file.content_type}",
            filename=file.filename,
        )


# ---------------------------------------------------------------------------
# Resume extraction
# ---------------------------------------------------------------------------


@router.post(
    "/extract-resume",
    response_model=ExtractionResponse,
    summary="Extract data from resume",
    description="""
Upload a doctor's resume (PDF or Image) and extract structured professional data.

**Supported formats:** PDF, PNG, JPG, JPEG

**Max file size:** 10MB

The extracted data includes:
- Personal details (name, email, title)
- Professional information (specialization, registration number)
- Qualifications (degrees, institutions, years)
- Expertise and skills
- Awards and memberships
- Practice locations

The response can be used to pre-fill the doctor registration form.
    """,
    responses={
        200: {
            "description": "Successfully extracted data",
            "model": ExtractionResponse,
        },
        400: {
            "description": "Invalid file or validation error",
        },
        422: {
            "description": "Failed to extract data from resume",
        },
        503: {
            "description": "AI service temporarily unavailable",
        },
    },
)
async def extract_resume(
    file: Annotated[UploadFile, File(description="Resume file (PDF, PNG, JPG)")],
    settings: Annotated[Settings, Depends(get_settings)],
    extraction_service: Annotated[Any, Depends(get_extraction_service)],
) -> ExtractionResponse:
    """
    Extract structured data from an uploaded resume.

    This endpoint:
    1. Validates the uploaded file (type, size)
    2. Sends it to Gemini Vision API for analysis
    3. Returns structured JSON matching the doctor schema

    The extracted data can be used to pre-fill registration forms,
    reducing manual data entry and improving accuracy.
    """
    # Validate file
    validate_file(file, settings)

    # Read file content
    content = await file.read()

    # Check file size
    if len(content) > settings.max_file_size_bytes:
        raise FileValidationError(
            message=f"File too large. Maximum size: {settings.MAX_FILE_SIZE_MB}MB",
            filename=file.filename,
        )

    log.info("resume_processing", filename=file.filename, size_bytes=len(content))

    # Extract data
    extracted_data, processing_time = await extraction_service.extract_from_file(
        file_content=content,
        filename=file.filename or "unknown",
    )

    return ExtractionResponse(
        success=True,
        message="Resume parsed successfully",
        data=extracted_data,
        processing_time_ms=round(processing_time, 2),
    )


# ---------------------------------------------------------------------------
# Submit (doctor self-service)
# ---------------------------------------------------------------------------


@router.post(
    "/submit/{doctor_id}",
    response_model=GenericResponse[dict[str, Any]],
    summary="Submit profile for verification",
    description="Submit the doctor's own profile for admin review. Requires authentication.",
)
async def submit_profile(
    doctor_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> GenericResponse[dict[str, Any]]:
    doctor_repo = DoctorRepository(db)
    repo = OnboardingRepository(db)

    # Update the primary doctors table
    doctor = await doctor_repo.get_by_id(doctor_id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    # Ownership guard: a regular user may only submit their own profile.
    # Admin and operation users may submit on behalf of any doctor.
    _elevated = current_user.role in (UserRole.ADMIN.value, UserRole.OPERATION.value)
    if not _elevated and current_user.doctor_id != doctor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only submit your own profile.",
        )

    now = datetime.now(UTC)
    previous_status = doctor.onboarding_status

    doctor.onboarding_status = OnboardingStatus.SUBMITTED.value
    doctor.updated_at = now

    # Ensure a doctor_identity row exists (required for FK in doctor_status_history).
    # OTP-created doctors may not have one yet — auto-create a minimal identity.
    identity = await repo.get_identity_by_doctor_id(doctor_id)
    if identity is None:
        import uuid as _uuid

        from ....models.onboarding import DoctorIdentity as _DoctorIdentity
        identity = _DoctorIdentity(
            id=str(_uuid.uuid4()),
            doctor_id=doctor_id,
            full_name=getattr(doctor, "full_name", None) or "",
            email=doctor.email or "",
            phone_number=doctor.phone or "",
            onboarding_status=OnboardingStatus.SUBMITTED,
        )
        db.add(identity)
        await db.flush()
    else:
        identity.onboarding_status = OnboardingStatus.SUBMITTED
        identity.updated_at = now
        identity.status_updated_at = now

    # Audit trail
    await repo.log_status_change(
        doctor_id=doctor_id,
        previous_status=previous_status,
        new_status=OnboardingStatus.SUBMITTED,
        changed_by=str(current_user.id),
    )

    await db.commit()
    await db.refresh(doctor)

    return GenericResponse(
        message="Profile submitted successfully",
        data={
            "doctor_id": doctor.id,
            "previous_status": previous_status,
            "new_status": doctor.onboarding_status,
        },
    )


# ---------------------------------------------------------------------------
# Email template prefetch (used by admin popup)
# ---------------------------------------------------------------------------


class EmailTemplateResponse(BaseModel):
    """Pre-rendered email template for the admin to review / edit before sending."""

    action: str = Field(..., description="'verified' or 'rejected'")
    doctor_id: int
    doctor_email: str
    subject: str = Field(..., description="Pre-filled email subject")
    body_html: str = Field(..., description="Pre-filled HTML email body")


@router.get(
    "/email-template/{doctor_id}",
    response_model=GenericResponse[EmailTemplateResponse],
    summary="Get pre-filled email template for admin popup (Admin/Operation only)",
    description="""
Fetch the pre-rendered email subject and body that will be shown to the admin
in the verification/rejection popup.

The admin can then edit these fields before clicking **Send** — the final
(possibly edited) content is passed back to the `verify` or `reject` endpoint.

**Query param `action`:**  `verified` or `rejected` (required)
    """,
)
async def get_email_template(
    doctor_id: int,
    db: DbSession,
    current_user: AdminOrOperationUser,
    email_svc: Annotated[EmailService, Depends(get_email_service)],
    action: Literal["verified", "rejected"] = Query(
        ...,
        description="Type of notification: 'verified' or 'rejected'",
    ),
) -> GenericResponse[EmailTemplateResponse]:
    """Return the pre-filled email template for the admin popup."""
    doctor_repo = DoctorRepository(db)
    doctor = await doctor_repo.get_by_id(doctor_id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    if not doctor.email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Doctor has no email address on record — cannot generate email template.",
        )

    template_vars = _doctor_template_vars(doctor, email_svc)
    rendered = email_svc.get_prefilled_template(action, template_vars)

    log.info(
        "email_template_fetched",
        doctor_id=doctor_id,
        action=action,
        admin_id=current_user.id,
    )

    return GenericResponse(
        message="Email template loaded successfully",
        data=EmailTemplateResponse(
            action=action,
            doctor_id=doctor_id,
            doctor_email=doctor.email,
            subject=rendered["subject"],
            body_html=rendered["body_html"],
        ),
    )


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


class VerifyProfilePayload(BaseModel):
    """Payload for verifying a doctor profile."""

    send_email: bool = Field(
        default=False,
        description="If true, send a verification notification email to the doctor.",
    )
    email_subject: str | None = Field(
        default=None,
        description="Custom email subject (admin-edited). Falls back to template default.",
    )
    email_body: str | None = Field(
        default=None,
        description="Custom HTML email body (admin-edited). Falls back to template default.",
    )


@router.post(
    "/verify/{doctor_id}",
    response_model=GenericResponse[dict[str, Any]],
    summary="Verify a doctor profile (Admin/Operation only)",
)
async def verify_profile(
    doctor_id: int,
    payload: VerifyProfilePayload,
    db: DbSession,
    current_user: AdminOrOperationUser,
    email_svc: Annotated[EmailService, Depends(get_email_service)],
) -> GenericResponse[dict[str, Any]]:
    """
    Mark a doctor profile as verified.

    Requires Admin or Operation role.
    Optionally send a verification notification email to the doctor by setting
    ``send_email=true`` in the request body.
    """
    doctor_repo = DoctorRepository(db)
    repo = OnboardingRepository(db)

    doctor = await doctor_repo.get_by_id(doctor_id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    now = datetime.now(UTC)
    previous_status = doctor.onboarding_status

    doctor.onboarding_status = OnboardingStatus.VERIFIED.value
    doctor.updated_at = now

    # Ensure a doctor_identity row exists (required for FK in doctor_status_history).
    identity = await repo.get_identity_by_doctor_id(doctor_id)
    if identity is None:
        import uuid as _uuid

        from ....models.onboarding import DoctorIdentity as _DoctorIdentity
        identity = _DoctorIdentity(
            id=str(_uuid.uuid4()),
            doctor_id=doctor_id,
            full_name=getattr(doctor, "full_name", None) or "",
            email=doctor.email or "",
            phone_number=doctor.phone or "",
            onboarding_status=OnboardingStatus.VERIFIED,
            verified_at=now,
            status_updated_at=now,
            status_updated_by=str(current_user.id),
        )
        db.add(identity)
        await db.flush()
    else:
        identity.onboarding_status = OnboardingStatus.VERIFIED
        identity.verified_at = now
        identity.status_updated_at = now
        identity.status_updated_by = str(current_user.id)
        identity.updated_at = now

    # Audit trail
    await repo.log_status_change(
        doctor_id=doctor_id,
        previous_status=previous_status,
        new_status=OnboardingStatus.VERIFIED,
        changed_by=str(current_user.id),
        changed_by_email=getattr(current_user, "email", None),
    )

    await db.commit()
    await db.refresh(doctor)

    # ------------------------------------------------------------------
    # Send email notification (non-blocking: failure does not roll back
    # the verification — the profile is already verified at this point)
    # ------------------------------------------------------------------
    email_sent = False
    email_error: str | None = None

    if payload.send_email:
        if not doctor.email:
            email_error = "Doctor has no email address on record."
            log.warning("email_skipped_no_address", doctor_id=doctor_id)
        else:
            try:
                template_vars = _doctor_template_vars(doctor, email_svc)
                await email_svc.send_notification(
                    to_address=doctor.email,
                    action="verified",
                    template_vars=template_vars,
                    subject_override=payload.email_subject,
                    body_html_override=payload.email_body,
                )
                email_sent = True
            except Exception as exc:  # noqa: BLE001
                email_error = str(exc)
                log.error(
                    "email_send_failed",
                    doctor_id=doctor_id,
                    error=email_error,
                )

    log.info(
        "profile_verified",
        doctor_id=doctor_id,
        previous_status=previous_status,
        admin_id=current_user.id,
        email_sent=email_sent,
    )

    return GenericResponse(
        message="Profile verified successfully",
        data={
            "doctor_id": doctor.id,
            "previous_status": previous_status,
            "new_status": doctor.onboarding_status,
            "verified_at": now.isoformat(),
            "email_sent": email_sent,
            **({"email_error": email_error} if email_error else {}),
        },
    )


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------


class RejectProfilePayload(BaseModel):
    """Payload for rejecting a doctor profile."""

    reason: str | None = Field(
        default=None,
        description="Human-readable rejection reason stored in the audit log.",
    )
    send_email: bool = Field(
        default=False,
        description="If true, send a rejection notification email to the doctor.",
    )
    email_subject: str | None = Field(
        default=None,
        description="Custom email subject (admin-edited). Falls back to template default.",
    )
    email_body: str | None = Field(
        default=None,
        description="Custom HTML email body (admin-edited). Falls back to template default.",
    )


@router.post(
    "/reject/{doctor_id}",
    response_model=GenericResponse[dict[str, Any]],
    summary="Reject a doctor profile (Admin/Operation only)",
)
async def reject_profile(
    doctor_id: int,
    payload: RejectProfilePayload,
    db: DbSession,
    current_user: AdminOrOperationUser,
    email_svc: Annotated[EmailService, Depends(get_email_service)],
) -> GenericResponse[dict[str, Any]]:
    """
    Mark a doctor profile as rejected.

    Requires Admin or Operation role.
    Optionally provide a rejection reason and send a notification email to the
    doctor by setting ``send_email=true`` in the request body.
    """
    doctor_repo = DoctorRepository(db)
    repo = OnboardingRepository(db)

    doctor = await doctor_repo.get_by_id(doctor_id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    now = datetime.now(UTC)
    previous_status = doctor.onboarding_status

    doctor.onboarding_status = OnboardingStatus.REJECTED.value
    doctor.updated_at = now

    # Ensure a doctor_identity row exists (required for FK in doctor_status_history).
    identity = await repo.get_identity_by_doctor_id(doctor_id)
    if identity is None:
        import uuid as _uuid

        from ....models.onboarding import DoctorIdentity as _DoctorIdentity
        identity = _DoctorIdentity(
            id=str(_uuid.uuid4()),
            doctor_id=doctor_id,
            full_name=getattr(doctor, "full_name", None) or "",
            email=doctor.email or "",
            phone_number=doctor.phone or "",
            onboarding_status=OnboardingStatus.REJECTED,
            rejection_reason=payload.reason,
            status_updated_at=now,
            status_updated_by=str(current_user.id),
        )
        db.add(identity)
        await db.flush()
    else:
        identity.onboarding_status = OnboardingStatus.REJECTED
        identity.rejection_reason = payload.reason
        identity.status_updated_at = now
        identity.status_updated_by = str(current_user.id)
        identity.updated_at = now

    # Audit trail
    await repo.log_status_change(
        doctor_id=doctor_id,
        previous_status=previous_status,
        new_status=OnboardingStatus.REJECTED,
        changed_by=str(current_user.id),
        changed_by_email=getattr(current_user, "email", None),
        rejection_reason=payload.reason,
    )

    await db.commit()
    await db.refresh(doctor)

    # ------------------------------------------------------------------
    # Send email notification (non-blocking — rejection is already committed)
    # ------------------------------------------------------------------
    email_sent = False
    email_error: str | None = None

    if payload.send_email:
        if not doctor.email:
            email_error = "Doctor has no email address on record."
            log.warning("email_skipped_no_address", doctor_id=doctor_id)
        else:
            try:
                template_vars = _doctor_template_vars(doctor, email_svc, reason=payload.reason or "")
                await email_svc.send_notification(
                    to_address=doctor.email,
                    action="rejected",
                    template_vars=template_vars,
                    subject_override=payload.email_subject,
                    body_html_override=payload.email_body,
                )
                email_sent = True
            except Exception as exc:  # noqa: BLE001
                email_error = str(exc)
                log.error(
                    "email_send_failed",
                    doctor_id=doctor_id,
                    error=email_error,
                )

    log.info(
        "profile_rejected",
        doctor_id=doctor_id,
        previous_status=previous_status,
        admin_id=current_user.id,
        email_sent=email_sent,
    )

    return GenericResponse(
        message="Profile rejected successfully",
        data={
            "doctor_id": doctor.id,
            "previous_status": previous_status,
            "new_status": doctor.onboarding_status,
            "reason": payload.reason,
            "email_sent": email_sent,
            **({"email_error": email_error} if email_error else {}),
        },
    )
