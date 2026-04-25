"""Authentication Endpoints for OTP-based login and Google Sign-In.

Provides endpoints for:
- POST /auth/otp/request      - Request OTP for mobile number
- POST /auth/otp/verify       - Verify OTP and login (doctor flow)
- POST /auth/otp/resend       - Resend OTP
- POST /auth/admin/otp/verify - Admin-only OTP verify (no auto-create)
- POST /auth/google/verify    - Google OAuth sign-in via Firebase
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import structlog
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status

from ....core.responses import GenericResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.config import Settings, get_settings
from ....db.session import get_db
from ....models.enums import UserRole
from ....models.user import User
from ....repositories.doctor_repository import DoctorRepository
from ....repositories.user_repository import UserRepository
from ....schemas.auth import (
    GoogleAuthSchema,
    OTPErrorResponse,
    OTPRequestResponse,
    OTPRequestSchema,
    OTPVerifyResponse,
    OTPVerifySchema,
)
from ....services.otp_service import OTPService, get_otp_service

logger = structlog.get_logger(__name__)

# Roles permitted to use the admin OTP endpoint
_ADMIN_ROLES: frozenset[str] = frozenset({UserRole.ADMIN.value, UserRole.OPERATION.value})


# ---------------------------------------------------------------------------
# JWT helpers (HS256, stdlib only — no external jwt library required)
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    """JWT access token response payload."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type, always 'bearer'")
    expires_in: int = Field(..., description="Token expiration time in seconds")


def _base64url_encode(data: bytes) -> str:
    """Encode bytes using base64 URL-safe encoding without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _encode_jwt(payload: dict[str, Any], *, secret: str, algorithm: str = "HS256") -> str:
    """Minimal HS256 JWT encoder using only the standard library."""
    if algorithm != "HS256":
        raise ValueError("Only HS256 algorithm is supported")

    header = {"alg": algorithm, "typ": "JWT"}
    header_json = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    encoded_header = _base64url_encode(header_json)
    encoded_payload = _base64url_encode(payload_json)

    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    encoded_signature = _base64url_encode(signature)

    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def _create_access_token(
    *,
    subject: str,
    settings: Settings,
    doctor_id: int | None = None,
    email: str | None = None,
    phone: str | None = None,
    role: str = "user",
) -> TokenResponse:
    """Create a signed JWT access token with user claims.

    ``subject`` is the login identifier (E.164 / 10-digit phone for OTP, or email for Google).
    ``phone`` is the doctor's phone when known (may be empty for email-first / Google users).
    """
    now = datetime.now(UTC)
    expire_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = now + expire_delta

    to_encode = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "doctor_id": doctor_id,
        "phone": phone or "",
        "email": email or "",
        "role": role,
    }

    encoded_jwt = _encode_jwt(to_encode, secret=settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return TokenResponse(
        access_token=encoded_jwt,
        token_type="bearer",
        expires_in=int(expire_delta.total_seconds()),
    )

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# POST /auth/otp/request
# ---------------------------------------------------------------------------

@router.post(
    "/otp/request",
    response_model=GenericResponse[OTPRequestResponse],
    status_code=status.HTTP_200_OK,
    summary="Request OTP",
    description="Send a 6-digit OTP to the provided mobile number for authentication.",
    responses={
        200: {"description": "OTP sent successfully"},
        500: {"description": "Failed to send OTP", "model": OTPErrorResponse},
    },
)
async def request_otp(
    request: OTPRequestSchema,
    otp_service: OTPService = Depends(get_otp_service),
) -> GenericResponse[OTPRequestResponse]:
    """Send OTP to mobile number.

    Sends a 6-digit OTP via SMS. OTP is valid for the duration
    configured via ``OTP_EXPIRY_SECONDS``.
    """
    logger.info("OTP request received", mobile=otp_service.mask_mobile(request.mobile_number))

    success, message = await otp_service.send_otp(
        request.mobile_number,
        delivery_method=request.delivery_method
    )

    if not success:
        logger.warning("OTP send failed", mobile=otp_service.mask_mobile(request.mobile_number))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "message": message,
                "error_code": "OTP_SEND_FAILED",
            },
        )

    return GenericResponse(
        message=message,
        data=OTPRequestResponse(
            success=True,
            message=message,
            mobile_number=otp_service.mask_mobile(request.mobile_number),
            expires_in_seconds=otp_service.settings.OTP_EXPIRY_SECONDS,
        ),
    )


# ---------------------------------------------------------------------------
# POST /auth/otp/verify
# ---------------------------------------------------------------------------

@router.post(
    "/otp/verify",
    response_model=GenericResponse[OTPVerifyResponse],
    status_code=status.HTTP_200_OK,
    summary="Verify OTP (Doctor)",
    description=(
        "Verify OTP and authenticate a doctor. Creates a new doctor record "
        "if the mobile number is not yet registered."
    ),
    responses={
        200: {"description": "OTP verified successfully"},
        401: {"description": "Invalid or expired OTP", "model": OTPErrorResponse},
    },
)
async def verify_otp(
    request: OTPVerifySchema,
    otp_service: OTPService = Depends(get_otp_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> GenericResponse[OTPVerifyResponse]:
    """Verify OTP and return a JWT for the doctor."""
    logger.info("OTP verify request", mobile=otp_service.mask_mobile(request.mobile_number))

    # 1. Verify OTP (skipped when SKIP_VERIFY is enabled)
    if settings.SKIP_VERIFY:
        logger.warning(
            "SKIP_VERIFY is enabled — OTP check bypassed (dev/test mode only)",
            mobile=otp_service.mask_mobile(request.mobile_number),
        )
    else:
        is_valid, message = await otp_service.verify_otp(request.mobile_number, request.otp)

        if not is_valid:
            error_code = "INVALID_OTP"
            if "expired" in message.lower():
                error_code = "OTP_EXPIRED"
            elif "attempts" in message.lower():
                error_code = "MAX_ATTEMPTS_EXCEEDED"
            elif "not found" in message.lower():
                error_code = "OTP_NOT_FOUND"

            logger.warning(
                "OTP verification failed",
                mobile=otp_service.mask_mobile(request.mobile_number),
                reason=message,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"success": False, "message": message, "error_code": error_code},
            )

    # 2. Find or auto-create doctor
    doctor_repo = DoctorRepository(db)
    user_repo = UserRepository(db)
    doctor = await doctor_repo.get_by_phone_number(request.mobile_number)
    is_new_user = doctor is None

    if doctor is None:
        doctor = await doctor_repo.create_from_phone(
            phone_number=request.mobile_number,
            role="user",
        )
        logger.info(
            "Created new doctor from OTP verification",
            doctor_id=doctor.id,
            mobile=otp_service.mask_mobile(request.mobile_number),
        )

    doctor_id = doctor.id
    doctor_email = doctor.email

    # 3. Ensure RBAC users row exists (get_or_create + race recovery). Never issue a
    #    JWT if we cannot resolve a User — otherwise get_current_user returns 401
    #    and the client session appears to "log out" on the next protected call.
    app_user: User | None = None
    try:
        app_user, _ = await user_repo.get_or_create(
            phone=request.mobile_number,
            email=doctor_email,
            doctor_id=doctor_id,
        )
    except IntegrityError as exc:
        await db.rollback()
        logger.warning("user_get_or_create_integrity", error=str(exc))
        app_user = await user_repo.get_by_phone(request.mobile_number)
        if app_user is None:
            app_user = await user_repo.get_by_doctor_id(doctor_id)
    except Exception as exc:
        await db.rollback()
        logger.warning("user_get_or_create_failed", error=str(exc))
        app_user = await user_repo.get_by_phone(request.mobile_number)
        if app_user is None:
            app_user = await user_repo.get_by_doctor_id(doctor_id)

    if app_user is None:
        logger.error("user_missing_after_otp_verify", doctor_id=doctor_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "message": "Account setup could not be completed. Please try again.",
                "error_code": "USER_SETUP_FAILED",
            },
        )

    user_role = app_user.role or "user"

    # 4. Issue JWT (subject stays the verified phone key used at login)
    token = _create_access_token(
        subject=request.mobile_number,
        settings=settings,
        doctor_id=doctor_id,
        email=doctor_email,
        phone=doctor.phone,
        role=user_role,
    )

    logger.info(
        "OTP verified successfully",
        mobile=otp_service.mask_mobile(request.mobile_number),
        is_new_user=is_new_user,
        doctor_id=doctor_id,
        role=user_role,
    )

    return GenericResponse(
        message="OTP verified successfully",
        data=OTPVerifyResponse(
            success=True,
            message="OTP verified successfully",
            doctor_id=doctor_id,
            is_new_user=is_new_user,
            mobile_number=request.mobile_number,
            email=doctor_email,
            role=user_role,
            access_token=token.access_token,
            token_type=token.token_type,
            expires_in=token.expires_in,
        ),
    )


# ---------------------------------------------------------------------------
# POST /auth/otp/resend
# ---------------------------------------------------------------------------

@router.post(
    "/otp/resend",
    response_model=GenericResponse[OTPRequestResponse],
    status_code=status.HTTP_200_OK,
    summary="Resend OTP",
    description="Generate a new OTP and resend it. Invalidates any previously issued OTP.",
    responses={
        200: {"description": "OTP resent successfully"},
        500: {"description": "Failed to resend OTP", "model": OTPErrorResponse},
    },
)
async def resend_otp(
    request: OTPRequestSchema,
    otp_service: OTPService = Depends(get_otp_service),
) -> GenericResponse[OTPRequestResponse]:
    """Resend (regenerate) OTP to the same mobile number."""
    logger.info("OTP resend request", mobile=otp_service.mask_mobile(request.mobile_number))

    success, message = await otp_service.send_otp(
        request.mobile_number,
        delivery_method=request.delivery_method
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "message": message, "error_code": "OTP_SEND_FAILED"},
        )

    return GenericResponse(
        message=message,
        data=OTPRequestResponse(
            success=True,
            message=message,
            mobile_number=otp_service.mask_mobile(request.mobile_number),
            expires_in_seconds=otp_service.settings.OTP_EXPIRY_SECONDS,
        ),
    )


# ---------------------------------------------------------------------------
# POST /auth/admin/otp/verify
# ---------------------------------------------------------------------------

@router.post(
    "/admin/otp/verify",
    response_model=GenericResponse[OTPVerifyResponse],
    status_code=status.HTTP_200_OK,
    summary="Verify Admin OTP",
    description=(
        "Verify OTP for admin/operation users. "
        "Strict RBAC: user must already exist with admin or operation role. "
        "New users are NEVER auto-created via this endpoint."
    ),
    responses={
        200: {"description": "Admin OTP verified successfully"},
        400: {"description": "Invalid / Expired OTP", "model": OTPErrorResponse},
        403: {"description": "Access denied (user not found or insufficient role)", "model": OTPErrorResponse},
    },
)
async def verify_admin_otp(
    request: OTPVerifySchema,
    otp_service: OTPService = Depends(get_otp_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> GenericResponse[OTPVerifyResponse]:
    """Verify OTP and authenticate a pre-registered admin or operation user.

    No user creation occurs here — the user must already exist in the ``users``
    table with ``admin`` or ``operation`` role.
    """
    logger.info("Admin OTP verify request", mobile=otp_service.mask_mobile(request.mobile_number))

    # 1. Verify OTP (skipped when SKIP_VERIFY is enabled)
    if settings.SKIP_VERIFY:
        logger.warning(
            "SKIP_VERIFY is enabled — Admin OTP check bypassed (dev/test mode only)",
            mobile=otp_service.mask_mobile(request.mobile_number),
        )
    else:
        is_valid, message = await otp_service.verify_otp(request.mobile_number, request.otp)

        if not is_valid:
            logger.warning(
                "Admin OTP verification failed",
                mobile=otp_service.mask_mobile(request.mobile_number),
                reason=message,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "message": message, "error_code": "INVALID_OTP"},
            )

    # 2. Strict user existence check — admins must be pre-provisioned
    user_repo = UserRepository(db)
    user = await user_repo.get_by_phone(request.mobile_number)

    if not user:
        logger.warning(
            "Admin login failed: user not found",
            mobile=otp_service.mask_mobile(request.mobile_number),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": "Access denied. Admin user not found.",
                "error_code": "USER_NOT_FOUND",
            },
        )

    # 3. RBAC — only admin and operation roles are permitted
    if user.role not in _ADMIN_ROLES:
        logger.warning(
            "Admin login failed: insufficient role",
            user_id=user.id,
            role=user.role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": "Access denied. Insufficient permissions.",
                "error_code": "INSUFFICIENT_PERMISSIONS",
            },
        )

    # 4. Active account check
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": "Account is inactive. Contact your administrator.",
                "error_code": "USER_INACTIVE",
            },
        )

    # 5. Issue JWT
    admin_subject = user.phone or user.email or ""
    token = _create_access_token(
        subject=admin_subject,
        settings=settings,
        doctor_id=user.doctor_id,
        email=user.email,
        phone=user.phone or "",
        role=user.role,
    )

    logger.info("Admin OTP verified successfully", user_id=user.id, role=user.role)

    return GenericResponse(
        message="Admin verified successfully",
        data=OTPVerifyResponse(
            success=True,
            message="Admin verified successfully",
            doctor_id=user.doctor_id,
            is_new_user=False,
            mobile_number=user.phone or "",
            email=user.email,
            role=user.role,
            access_token=token.access_token,
            token_type=token.token_type,
            expires_in=token.expires_in,
        ),
    )


# ---------------------------------------------------------------------------
# POST /auth/google/verify
# ---------------------------------------------------------------------------

@router.post(
    "/google/verify",
    response_model=GenericResponse[OTPVerifyResponse],
    status_code=status.HTTP_200_OK,
    summary="Google Sign-In",
    description=(
        "Verify a Firebase ID token obtained from Google Sign-In. "
        "Finds or creates the doctor record by email. No OTP step is required."
    ),
    responses={
        200: {"description": "Google Sign-In successful"},
        400: {"description": "No email in Google account", "model": OTPErrorResponse},
        401: {"description": "Invalid Firebase token", "model": OTPErrorResponse},
    },
)
async def google_verify(
    request: GoogleAuthSchema,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> GenericResponse[OTPVerifyResponse]:
    """Verify Google Sign-In Firebase token and return a JWT.

    Flow:
        1. Verify Firebase ID token server-side.
        2. Extract ``email`` and ``name`` from the decoded token payload.
        3. Find or create a doctor record keyed on the email address.
        4. Find or create a user record (RBAC) keyed on the email address.
        5. Issue and return a JWT access token.
    """
    from ....core.firebase_config import verify_firebase_token

    logger.info("Google Sign-In verify request received")

    # 1. Verify Firebase ID token (async — must be awaited)
    try:
        decoded_token = await verify_firebase_token(request.id_token)
    except ValueError as exc:
        logger.warning("Google Sign-In: invalid token", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "message": str(exc),
                "error_code": "INVALID_FIREBASE_TOKEN",
            },
        )

    # 2. Extract claims
    google_email_raw: str | None = decoded_token.get("email")
    google_name: str = decoded_token.get("name", "")

    if not google_email_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "message": "No email found in Google account.",
                "error_code": "NO_EMAIL",
            },
        )

    google_email = google_email_raw.strip().lower()

    logger.info("Google Sign-In: token decoded", email=google_email, name=google_name)

    # 3. Find or create doctor
    doctor_repo = DoctorRepository(db)
    user_repo = UserRepository(db)
    doctor = await doctor_repo.get_by_email(google_email)
    is_new_user = doctor is None

    if doctor is None:
        doctor = await doctor_repo.create_from_email(
            email=google_email,
            name=google_name,
            role="user",
        )
        logger.info("Created new doctor from Google Sign-In", doctor_id=doctor.id, email=google_email)

    doctor_id = doctor.id
    doctor_phone: str | None = doctor.phone or None

    # 4. Find or create user record (RBAC)
    # For Google users without a phone we use the email as the unique lookup key.
    existing_user = await user_repo.get_by_email(google_email)
    if existing_user:
        user_role = existing_user.role or "user"
    else:
        user_role = "user"
        # Only pass phone if we actually have a real one; otherwise leave it as
        # None so the unique constraint on phone is not violated by a
        # placeholder value that could collide across multiple Google users.
        try:
            await user_repo.create(
                phone=doctor_phone,
                email=google_email.lower(),
                role=user_role,
                is_active=True,
                doctor_id=doctor_id,
            )
        except Exception as exc:
            # Tolerate duplicate-key races; role resolved above remains "user"
            logger.warning("User record creation skipped (may already exist)", error=str(exc))
            await db.rollback()

    # 4b. Prefer role from persisted user (covers create races / email vs row drift)
    persisted_user = await user_repo.get_by_email(google_email) or await user_repo.get_by_doctor_id(doctor_id)
    if persisted_user is not None:
        user_role = persisted_user.role or "user"

    # 5. Issue JWT — email is ``sub`` so RBAC can resolve the user before phone is collected in onboarding
    token = _create_access_token(
        subject=google_email,
        settings=settings,
        doctor_id=doctor_id,
        email=google_email,
        phone=doctor_phone or "",
        role=user_role,
    )

    logger.info(
        "Google Sign-In successful",
        email=google_email,
        is_new_user=is_new_user,
        doctor_id=doctor_id,
    )

    return GenericResponse(
        message="Google Sign-In successful",
        data=OTPVerifyResponse(
            success=True,
            message="Google Sign-In successful",
            doctor_id=doctor_id,
            is_new_user=is_new_user,
            mobile_number=doctor_phone or "",
            email=google_email,
            role=user_role,
            access_token=token.access_token,
            token_type=token.token_type,
            expires_in=token.expires_in,
        ),
    )
