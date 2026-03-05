"""Admin CRUD endpoints for onboarding tables.

Exposes administration operations over doctor onboarding data:
  - doctor_identity    : POST /identities, GET /identities
  - doctor_media       : POST/GET /media/{doctor_id}, DELETE /media/{media_id},
                         POST /media/{doctor_id}/upload
  - doctor_status_history : POST/GET /status-history/{doctor_id}

NOTE: The aggregated doctor list and lookup routes formerly at
  GET /onboarding-admin/doctors
  GET /onboarding-admin/doctors/lookup
have been consolidated into the main /doctors endpoint:
  GET /doctors          (add ?status= for full onboarding info)
  GET /doctors/lookup

All routes require Admin or Operational role (enforced at each endpoint
via ``AdminOrOperationalUser`` in addition to the router-level
``require_authentication`` dependency set in ``v1/__init__.py``).
"""
from __future__ import annotations

from collections.abc import Sequence

import structlog
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi import status as http_status

from ....core.rbac import AdminOrOperationalUser
from ....db.session import DbSession
from ....repositories import OnboardingRepository
from ....schemas import (
    DoctorIdentityCreate,
    DoctorIdentityResponse,
    DoctorMediaCreate,
    DoctorMediaResponse,
    DoctorStatusHistoryCreate,
    DoctorStatusHistoryResponse,
)
from ....services.blob_storage_service import S3BlobStorageService, get_blob_storage_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/onboarding-admin", tags=["Onboarding Admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_absolute_uri(request: Request, file_uri: str) -> str:
    """Return an absolute URL for ``file_uri``.

    Already-absolute URIs (http/https) are returned unchanged; relative URIs
    are prefixed with the current request base URL.
    """
    if file_uri.startswith("http://") or file_uri.startswith("https://"):
        return file_uri
    base = str(request.base_url).rstrip("/")
    if file_uri.startswith("/"):
        return f"{base}{file_uri}"
    return f"{base}/{file_uri}"

async def _sign_media_url(media: DoctorMediaResponse) -> DoctorMediaResponse:
    """Dynamically generate signed S3 URL for media file_uri."""
    blob_service = get_blob_storage_service()
    
    if not isinstance(blob_service, S3BlobStorageService) or not blob_service.use_signed_urls:
        return media

    uri = media.file_uri
    if not uri or "s3" not in uri.lower():
        return media
        
    try:
        parts = uri.split(".amazonaws.com/")
        if len(parts) == 2:
            key = parts[1]
            async with blob_service.session.client("s3") as s3_client:
                media.file_uri = str(await s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": blob_service.bucket_name, "Key": key},
                    ExpiresIn=blob_service.signed_url_expiry,
                ))
    except Exception as e:
        log.warning("Failed to sign media URL: %s, error=%s", uri, str(e))
        
    return media


# ---------------------------------------------------------------------------
# doctor_identity
# ---------------------------------------------------------------------------


@router.post(
    "/identities",
    response_model=DoctorIdentityResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create doctor identity record (Admin/Operational only)",
)
async def create_identity(
    payload: DoctorIdentityCreate,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> DoctorIdentityResponse:
    """Create a new ``doctor_identity`` row.

    Requires Admin or Operational role.
    """
    repo = OnboardingRepository(db)
    log.info(
        "admin_identity_create",
        admin_id=current_user.id,
        email=payload.email,
    )
    return await repo.create_identity(**payload.model_dump())  # type: ignore[return-value]


@router.get(
    "/identities",
    response_model=DoctorIdentityResponse,
    summary="Fetch doctor identity by doctor_id or email (Admin/Operational only)",
)
async def get_identity(
    db: DbSession,
    current_user: AdminOrOperationalUser,
    doctor_id: int | None = Query(None, description="Lookup by doctor ID"),
    email: str | None = Query(None, description="Lookup by email"),
) -> DoctorIdentityResponse:
    """Return the ``doctor_identity`` row for a given ``doctor_id`` or ``email``.

    Requires Admin or Operational role.
    """
    repo = OnboardingRepository(db)

    if doctor_id:
        identity = await repo.get_identity_by_doctor_id(doctor_id)
    elif email:
        identity = await repo.get_identity_by_email(email)
    else:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Provide either doctor_id or email.",
        )

    if not identity:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Doctor identity not found.",
        )

    return identity  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# doctor_media
# ---------------------------------------------------------------------------


@router.post(
    "/media/{doctor_id}",
    response_model=DoctorMediaResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Add media record for a doctor (Admin/Operational only)",
)
async def add_media(
    doctor_id: int,
    payload: DoctorMediaCreate,
    db: DbSession,
    request: Request,
    current_user: AdminOrOperationalUser,
) -> DoctorMediaResponse:
    """Insert a ``doctor_media`` row and return the absolute file URI.

    Requires Admin or Operational role.
    """
    repo = OnboardingRepository(db)
    media = await repo.add_media(doctor_id=doctor_id, **payload.model_dump())
    media.file_uri = _build_absolute_uri(request, media.file_uri)
    log.info(
        "admin_media_added",
        doctor_id=doctor_id,
        media_id=media.media_id,
        admin_id=current_user.id,
    )
    return await _sign_media_url(media)


@router.get(
    "/media/{doctor_id}",
    response_model=list[DoctorMediaResponse],
    summary="List media for a doctor (Admin/Operational only)",
)
async def list_media(
    doctor_id: int,
    db: DbSession,
    request: Request,
    current_user: AdminOrOperationalUser,
) -> Sequence[DoctorMediaResponse]:
    """Return all ``doctor_media`` rows for ``doctor_id`` with absolute URIs.

    Requires Admin or Operational role.
    """
    repo = OnboardingRepository(db)
    media = await repo.list_media(doctor_id)
    for item in media:
        item.file_uri = _build_absolute_uri(request, item.file_uri)
    return [await _sign_media_url(item) for item in media]


@router.delete(
    "/media/{media_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a media record (Admin/Operational only)",
)
async def delete_media(
    media_id: str,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> None:
    """Delete a ``doctor_media`` row by its UUID ``media_id``.

    Requires Admin or Operational role.
    """
    repo = OnboardingRepository(db)
    deleted = await repo.delete_media(media_id)
    if not deleted:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Media not found.",
        )
    log.info("admin_media_deleted", media_id=media_id, admin_id=current_user.id)


@router.post(
    "/media/{doctor_id}/upload",
    response_model=DoctorMediaResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Upload a file for a doctor profile (Admin/Operational only)",
    description=(
        "Upload a file directly to blob storage and register its metadata in "
        "``doctor_media``. Supported: images (JPG, PNG, GIF) and documents (PDF). "
        "Maximum size: 50 MB."
    ),
)
async def upload_media_file(
    doctor_id: int,
    media_category: str,
    db: DbSession,
    request: Request,
    current_user: AdminOrOperationalUser,
    field_name: str | None = None,
    file: UploadFile = File(...),
) -> DoctorMediaResponse:
    """Upload a file to blob storage and register it in the database.

    Requires Admin or Operational role.

    Args:
        doctor_id:      Numeric doctor identifier.
        media_category: Category key, e.g. ``profile_photo``, ``certificate``, ``resume``.
        field_name:     Logical field key for ``media_urls`` — defaults to ``media_category``.
        file:           The multipart file upload.
    """
    repo = OnboardingRepository(db)
    blob_service = get_blob_storage_service()

    # Verify the doctor exists before uploading
    identity = await repo.get_identity_by_doctor_id(doctor_id)
    if identity is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Doctor not found.",
        )

    file_content = await file.read()
    file_name = file.filename or "uploaded_file"

    log.info(
        "admin_file_upload_start",
        doctor_id=doctor_id,
        media_category=media_category,
        file_name=file_name,
        size_bytes=len(file_content),
        admin_id=current_user.id,
    )

    upload_result = await blob_service.upload_from_bytes(
        content=file_content,
        file_name=file_name,
        doctor_id=doctor_id,
        media_category=media_category,
    )

    if not upload_result.success:
        log.error(
            "admin_file_upload_failed",
            file_name=file_name,
            error=upload_result.error_message,
            admin_id=current_user.id,
        )
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"File upload failed: {upload_result.error_message}",
        )

    media_type = (
        "image"
        if (file.content_type and file.content_type.startswith("image/"))
        else "document"
    )

    media = await repo.add_media(
        doctor_id=doctor_id,
        media_type=media_type,
        media_category=media_category,
        field_name=field_name or media_category,
        file_uri=upload_result.file_uri,
        file_name=file_name,
        file_size=len(file_content),
        mime_type=file.content_type,
    )
    media.file_uri = upload_result.file_uri

    log.info(
        "admin_file_upload_complete",
        media_id=media.media_id,
        file_uri=upload_result.file_uri,
        admin_id=current_user.id,
    )
    
    media.file_uri = _build_absolute_uri(request, media.file_uri)
    return await _sign_media_url(media)


# ---------------------------------------------------------------------------
# doctor_status_history
# ---------------------------------------------------------------------------


@router.post(
    "/status-history/{doctor_id}",
    response_model=DoctorStatusHistoryResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Log a status change for a doctor (Admin/Operational only)",
)
async def log_status_history(
    doctor_id: int,
    payload: DoctorStatusHistoryCreate,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> DoctorStatusHistoryResponse:
    """Append a status-change entry to ``doctor_status_history``.

    Requires Admin or Operational role.
    """
    repo = OnboardingRepository(db)
    log.info(
        "admin_status_history_log",
        doctor_id=doctor_id,
        admin_id=current_user.id,
    )
    return await repo.log_status_change(doctor_id=doctor_id, **payload.model_dump())  # type: ignore[return-value]


@router.get(
    "/status-history/{doctor_id}",
    response_model=list[DoctorStatusHistoryResponse],
    summary="Fetch status history for a doctor (Admin/Operational only)",
)
async def get_status_history(
    doctor_id: int,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> Sequence[DoctorStatusHistoryResponse]:
    """Return all status-history entries for ``doctor_id``.

    Requires Admin or Operational role.
    """
    repo = OnboardingRepository(db)
    return list(await repo.get_status_history(doctor_id))  # type: ignore[arg-type]


# NOTE: The aggregated list and lookup routes that were previously here
# (GET /onboarding-admin/doctors and GET /onboarding-admin/doctors/lookup)
# have been consolidated into GET /doctors and GET /doctors/lookup
# in src/app/api/v1/endpoints/doctors.py to reduce API surface duplication.
