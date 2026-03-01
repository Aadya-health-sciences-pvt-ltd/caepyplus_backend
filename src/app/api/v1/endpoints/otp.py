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
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.config import Settings, get_settings
from ....db.session import get_db
from ....models.enums import UserRole
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
_ADMIN_ROLES: frozenset[str] = frozenset({UserRole.ADMIN.value, UserRole.OPERATIONAL.value})


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
    role: str = "user",
) -> TokenResponse:
    """Create a signed JWT access token with user claims."""
    now = datetime.now(UTC)
    expire_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = now + expire_delta

    to_encode = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "doctor_id": doctor_id,
        "phone": subject,
        "email": email,
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
    response_model=OTPRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Request OTP",
    description="Send a 6-digit OTP to the provided mobile number for authentication.",
    responses={
        200: {"description": "OTP sent successfully", "model": OTPRequestResponse},
        500: {"description": "Failed to send OTP", "model": OTPErrorResponse},
    },
)
async def request_otp(
    request: OTPRequestSchema,
    otp_service: OTPService = Depends(get_otp_service),
) -> OTPRequestResponse:
    """Send OTP to mobile number.

    Sends a 6-digit OTP via SMS. OTP is valid for the duration
    configured via ``OTP_EXPIRY_SECONDS``.
    """
    logger.info("OTP request received", mobile=otp_service.mask_mobile(request.mobile_number))

    success, message = await otp_service.send_otp(request.mobile_number)

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

    return OTPRequestResponse(
        success=True,
        message=message,
        mobile_number=otp_service.mask_mobile(request.mobile_number),
        expires_in_seconds=otp_service.settings.OTP_EXPIRY_SECONDS,
    )


# ---------------------------------------------------------------------------
# POST /auth/otp/verify
# ---------------------------------------------------------------------------

@router.post(
    "/otp/verify",
    response_model=OTPVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify OTP (Doctor)",
    description=(
        "Verify OTP and authenticate a doctor. Creates a new doctor record "
        "if the mobile number is not yet registered."
    ),
    responses={
        200: {"description": "OTP verified successfully", "model": OTPVerifyResponse},
        401: {"description": "Invalid or expired OTP", "model": OTPErrorResponse},
    },
)
async def verify_otp(
    request: OTPVerifySchema,
    otp_service: OTPService = Depends(get_otp_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OTPVerifyResponse:
    """Verify OTP and return a JWT for the doctor."""
    logger.info("OTP verify request", mobile=otp_service.mask_mobile(request.mobile_number))

    # 1. Verify OTP — always enforce real OTP check
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

    # 3. Resolve role from users table (single source of truth for RBAC)
    existing_user = await user_repo.get_by_phone(request.mobile_number)
    if existing_user:
        user_role = existing_user.role or "user"
    else:
        user_role = "user"
        try:
            await user_repo.create(
                phone=request.mobile_number,
                email=doctor_email,
                role=user_role,
                is_active=True,
                doctor_id=doctor_id,
            )
        except Exception as exc:
            # Tolerate race-condition duplicates; role is already "user"
            logger.warning("User record creation skipped (may already exist)", error=str(exc))

    # 4. Issue JWT
    token = _create_access_token(
        subject=request.mobile_number,
        settings=settings,
        doctor_id=doctor_id,
        email=doctor_email,
        role=user_role,
    )

    logger.info(
        "OTP verified successfully",
        mobile=otp_service.mask_mobile(request.mobile_number),
        is_new_user=is_new_user,
        doctor_id=doctor_id,
        role=user_role,
    )

    return OTPVerifyResponse(
        success=True,
        message="OTP verified successfully",
        doctor_id=doctor_id,
        is_new_user=is_new_user,
        mobile_number=request.mobile_number,
        role=user_role,
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
    )


# ---------------------------------------------------------------------------
# POST /auth/otp/resend
# ---------------------------------------------------------------------------

@router.post(
    "/otp/resend",
    response_model=OTPRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend OTP",
    description="Generate a new OTP and resend it. Invalidates any previously issued OTP.",
    responses={
        200: {"description": "OTP resent successfully", "model": OTPRequestResponse},
        500: {"description": "Failed to resend OTP", "model": OTPErrorResponse},
    },
)
async def resend_otp(
    request: OTPRequestSchema,
    otp_service: OTPService = Depends(get_otp_service),
) -> OTPRequestResponse:
    """Resend (regenerate) OTP to the same mobile number."""
    logger.info("OTP resend request", mobile=otp_service.mask_mobile(request.mobile_number))

    success, message = await otp_service.send_otp(request.mobile_number)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "message": message, "error_code": "OTP_SEND_FAILED"},
        )

    return OTPRequestResponse(
        success=True,
        message="OTP resent successfully",
        mobile_number=otp_service.mask_mobile(request.mobile_number),
        expires_in_seconds=otp_service.settings.OTP_EXPIRY_SECONDS,
    )


# ---------------------------------------------------------------------------
# POST /auth/admin/otp/verify
# ---------------------------------------------------------------------------

@router.post(
    "/admin/otp/verify",
    response_model=OTPVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify Admin OTP",
    description=(
        "Verify OTP for admin/operational users. "
        "Strict RBAC: user must already exist with admin or operational role. "
        "New users are NEVER auto-created via this endpoint."
    ),
    responses={
        200: {"description": "Admin OTP verified successfully", "model": OTPVerifyResponse},
        400: {"description": "Invalid / Expired OTP", "model": OTPErrorResponse},
        403: {"description": "Access denied (user not found or insufficient role)", "model": OTPErrorResponse},
    },
)
async def verify_admin_otp(
    request: OTPVerifySchema,
    otp_service: OTPService = Depends(get_otp_service),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OTPVerifyResponse:
    """Verify OTP and authenticate a pre-registered admin or operational user.

    No user creation occurs here — the user must already exist in the ``users``
    table with ``admin`` or ``operational`` role.
    """
    logger.info("Admin OTP verify request", mobile=otp_service.mask_mobile(request.mobile_number))

    # 1. Verify OTP — no bypass, always enforce real OTP verification
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

    # 3. RBAC — only admin and operational roles are permitted
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
    token = _create_access_token(
        subject=user.phone,
        settings=settings,
        doctor_id=user.doctor_id,
        email=user.email,
        role=user.role,
    )

    logger.info("Admin OTP verified successfully", user_id=user.id, role=user.role)

    return OTPVerifyResponse(
        success=True,
        message="Admin verified successfully",
        doctor_id=user.doctor_id,  # May be None if not linked to a doctor record
        is_new_user=False,
        mobile_number=user.phone,
        role=user.role,
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
    )


# ---------------------------------------------------------------------------
# POST /auth/google/verify
# ---------------------------------------------------------------------------

@router.post(
    "/google/verify",
    response_model=OTPVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Google Sign-In",
    description=(
        "Verify a Firebase ID token obtained from Google Sign-In. "
        "Finds or creates the doctor record by email. No OTP step is required."
    ),
    responses={
        200: {"description": "Google Sign-In successful", "model": OTPVerifyResponse},
        400: {"description": "No email in Google account", "model": OTPErrorResponse},
        401: {"description": "Invalid Firebase token", "model": OTPErrorResponse},
    },
)
async def google_verify(
    request: GoogleAuthSchema,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OTPVerifyResponse:
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
    google_email: str | None = decoded_token.get("email")
    google_name: str = decoded_token.get("name", "")

    if not google_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "message": "No email found in Google account.",
                "error_code": "NO_EMAIL",
            },
        )

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
                email=google_email,
                role=user_role,
                is_active=True,
                doctor_id=doctor_id,
            )
        except Exception as exc:
            # Tolerate duplicate-key races; role resolved above remains "user"
            logger.warning("User record creation skipped (may already exist)", error=str(exc))

    # 5. Issue JWT — use email as subject for Google users
    token = _create_access_token(
        subject=google_email,
        settings=settings,
        doctor_id=doctor_id,
        email=google_email,
        role=user_role,
    )

    logger.info(
        "Google Sign-In successful",
        email=google_email,
        is_new_user=is_new_user,
        doctor_id=doctor_id,
    )

    return OTPVerifyResponse(
        success=True,
        message="Google Sign-In successful",
        doctor_id=doctor_id,
        is_new_user=is_new_user,
        mobile_number=doctor_phone or "",
        role=user_role,
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
    )
