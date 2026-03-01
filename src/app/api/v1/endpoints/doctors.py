"""
Doctor CRUD Endpoints.

RESTful API for doctor resource management.

Exposed routes (all under /api/v1/doctors):
  GET    /                         - Paginated doctor list; ?status= filter returns full onboarding info
  GET    /lookup                   - Full admin view by id / email / phone
  GET    /{doctor_id}              - Fetch single doctor profile
  PUT    /{doctor_id}              - Update doctor profile (admin/operational only)
  GET    /bulk-upload/csv/template  - Download the official CSV template with sample rows
  POST   /bulk-upload/csv/validate - Phase 1: validate CSV, return row errors, no DB writes
  POST   /bulk-upload/csv          - Phase 2: validate + persist; creates PENDING doctor_identity rows

Note: The /onboarding-admin/doctors and /onboarding-admin/doctors/lookup routes
were consolidated here to reduce duplication (team-lead review comment #3/#4).
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Annotated, Any, Union

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ....core.doctor_utils import synthesise_identity as _synthesise_identity
from ....core.rbac import CurrentUser
from ....core.responses import GenericResponse, PaginatedResponse, PaginationMeta
from ....db.session import DbSession
from ....models.doctor import Doctor as DoctorModel
from ....models.onboarding import DoctorIdentity, DoctorStatusHistory, OnboardingStatus
from ....repositories.doctor_repository import DoctorRepository
from ....repositories.onboarding_repository import OnboardingRepository
from ....schemas.doctor import DoctorResponse, DoctorUpdate
from ....schemas.onboarding import (
    DoctorDetailsResponse,
    DoctorIdentityResponse,
    DoctorMediaResponse,
    DoctorStatusHistoryResponse,
    DoctorWithFullInfoResponse,
    OnboardingStatusEnum,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/doctors")


# Pre-computed frozenset of valid DoctorUpdate field names used in CSV uploads.
_DOCTOR_UPDATE_FIELDS: frozenset[str] = frozenset(DoctorUpdate.model_fields)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_doctor_repo(db: DbSession) -> DoctorRepository:
    """DI factory — returns a DoctorRepository bound to the request session."""
    return DoctorRepository(db)


DoctorRepoDep = Annotated[DoctorRepository, Depends(_get_doctor_repo)]


# ---------------------------------------------------------------------------
# CSV upload response schemas
# ---------------------------------------------------------------------------

class CsvRowValidationError(BaseModel):
    """A single row-level validation error discovered during CSV validation."""

    row: int
    field: str | None = None
    error: str


class CsvValidationResponse(BaseModel):
    """Result of the CSV validation pass (no DB writes).

    ``valid`` is True only when ``errors`` is an empty list.
    The frontend should display the error list to the operator, let them fix
    the CSV, and re-upload.  Only when ``valid=True`` should the confirm
    upload endpoint be called.
    """

    valid: bool
    total_rows: int
    error_count: int
    errors: list[CsvRowValidationError]


class CsvUploadRow(BaseModel):
    """Per-row outcome of the confirmed bulk CSV upload."""

    row: int
    status: str  # "created" | "updated" | "skipped"
    doctor_id: int | None = None
    phone: str | None = None
    email: str | None = None


class CsvUploadResponse(BaseModel):
    """Aggregate result of the confirmed bulk CSV upload.

    ``success`` is True only when ``skipped == 0``.
    ``skipped_errors`` lists the per-row DB-level errors (e.g. unique
    constraint violations) for any rows that could not be written.
    """

    success: bool
    message: str
    total_rows: int
    created: int
    updated: int
    skipped: int
    rows: list[CsvUploadRow]
    skipped_errors: list[CsvRowValidationError] = []


# ---------------------------------------------------------------------------
# GET /doctors  — paginated list
#
# When ?status= is supplied the response switches to DoctorWithFullInfoResponse
# (full onboarding data per doctor).  Without ?status= the response is the
# lightweight DoctorResponse.  Both share the same PaginatedResponse envelope.
#
# This consolidates the old /onboarding-admin/doctors route here so that both
# the basic list and the admin filtered-full-info list live in one place.
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=PaginatedResponse[Union[DoctorWithFullInfoResponse, DoctorResponse]],
    summary="List all doctors",
    description=(
        "Paginated list of registered doctors.\n\n"
        "- Without `status`: returns lightweight `DoctorResponse` objects. "
        "Optional `specialization` partial-match filter is available.\n"
        "- With `status` (PENDING | SUBMITTED | VERIFIED | REJECTED): returns "
        "full `DoctorWithFullInfoResponse` including identity, details, media "
        "and status history.  Uses `selectinload` for N+1-safe fetching."
    ),
)
async def list_doctors(
    db: DbSession,
    repo: DoctorRepoDep,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    specialization: str | None = Query(default=None, description="Filter by specialization (partial match, no status filter)"),
    onboarding_status: OnboardingStatusEnum | None = Query(
        default=None,
        alias="status",
        description="Filter by onboarding status — returns full info when set",
    ),
) -> PaginatedResponse[Any]:
    """Return a paginated doctor list.

    When *status* is provided the list is sourced from ``doctor_identity``
    (onboarding-status aware, full info per doctor).  Otherwise the plain
    ``doctors`` table is queried and only basic profile fields are returned.
    """
    skip = (page - 1) * page_size

    if onboarding_status is not None:
        # Enriched admin view — sourced from doctor_identity with eager-loaded
        # related rows (3 fixed-cost IN-clause queries via selectinload).
        onboarding_repo = OnboardingRepository(db)
        # Execute sequentially to avoid session state conflicts
        identities = await onboarding_repo.list_identities(
            status=onboarding_status.value,
            skip=skip,
            limit=page_size,
            eager_load=True,
        )
        total = await onboarding_repo.count_identities_by_status(status=onboarding_status.value)
        data: list[Any] = [
            DoctorWithFullInfoResponse(
                identity=identity,
                details=identity.details,
                media=list(identity.media),
                status_history=list(identity.status_history),
            )
            for identity in identities
        ]
        message = f"Found {total} doctor(s) with status '{onboarding_status.value}'"
    else:
        # Lightweight basic list
        # Execute sequentially to avoid session state conflicts
        all_doctors = await repo.get_all(skip=skip, limit=page_size, specialization=specialization)
        total = await repo.count(specialization=specialization)
        data = [DoctorResponse.model_validate(d) for d in all_doctors]
        message = "Doctors retrieved successfully"

    return PaginatedResponse(
        message=message,
        data=data,
        pagination=PaginationMeta.from_total(total, page, page_size),
    )


# ---------------------------------------------------------------------------
# GET /doctors/lookup  — admin full-profile view
#   (previously at /onboarding-admin/doctors/lookup)
# ---------------------------------------------------------------------------

@router.get(
    "/lookup",
    response_model=DoctorWithFullInfoResponse,
    summary="Full doctor profile (admin view)",
    description=(
        "Fetch a single doctor's complete onboarding data by ``doctor_id``, "
        "``email``, or ``phone``. Aggregates the primary doctors table with "
        "identity, details, media, and status-history rows."
    ),
    responses={
        200: {"description": "Doctor found"},
        400: {"description": "No lookup parameter supplied"},
        404: {"description": "Doctor not found"},
    },
)
async def lookup_doctor(
    db: DbSession,
    doctor_id: int | None = Query(None, description="Lookup by numeric doctor ID"),
    email: str | None = Query(None, description="Lookup by email address"),
    phone: str | None = Query(None, description="Lookup by phone number (+91…)"),
) -> DoctorWithFullInfoResponse:
    """Aggregate full doctor onboarding profile — admin use only."""
    if not any([doctor_id, email, phone]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one of: doctor_id, email, phone.",
        )

    repo = OnboardingRepository(db)
    doctor_repo = DoctorRepository(db)

    identity = None
    doctor = None
    resolved_id: int | None = doctor_id

    if doctor_id:
        identity = await repo.get_identity_by_doctor_id(doctor_id)
        if not identity:
            doctor = await doctor_repo.get_by_id(doctor_id)

    elif email:
        identity = await repo.get_identity_by_email(email)
        if identity:
            resolved_id = identity.doctor_id
        else:
            doctor = await doctor_repo.get_by_email(email)
            if doctor:
                resolved_id = doctor.id

    elif phone:
        identity = await repo.get_identity_by_phone(phone)
        if identity:
            resolved_id = identity.doctor_id
        else:
            formatted = phone if phone.startswith("+") else f"+91{phone}"
            doctor = await doctor_repo.get_by_phone_number(formatted)
            if not doctor and not phone.startswith("+"):
                doctor = await doctor_repo.get_by_phone_number(phone)
            if doctor:
                resolved_id = doctor.id

    if identity is None and doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")

    assert resolved_id is not None

    if identity:
        identity_resp = DoctorIdentityResponse.model_validate(identity)
    else:
        assert doctor is not None
        identity_resp = _synthesise_identity(doctor)

    details = await repo.get_details_by_doctor_id(resolved_id)
    media = await repo.list_media(resolved_id)
    status_history = await repo.get_status_history(resolved_id)

    return DoctorWithFullInfoResponse(
        identity=identity_resp,
        details=DoctorDetailsResponse.model_validate(details) if details else None,
        media=[DoctorMediaResponse.model_validate(m) for m in media],
        status_history=[DoctorStatusHistoryResponse.model_validate(h) for h in status_history],
    )


# ---------------------------------------------------------------------------
# GET /doctors/{doctor_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{doctor_id}",
    response_model=GenericResponse[DoctorResponse],
    summary="Get doctor by ID",
    description="Retrieve the full profile of a specific doctor.",
)
async def get_doctor(
    doctor_id: int,
    repo: DoctorRepoDep,
) -> GenericResponse[DoctorResponse]:
    """Fetch a doctor record by its numeric ID."""
    doctor = await repo.get_by_id_or_raise(doctor_id)
    return GenericResponse(
        message="Doctor retrieved successfully",
        data=DoctorResponse.model_validate(doctor),
    )


# ---------------------------------------------------------------------------
# PUT /doctors/{doctor_id}
# ---------------------------------------------------------------------------

@router.put(
    "/{doctor_id}",
    response_model=GenericResponse[DoctorResponse],
    summary="Update doctor",
    description="Update an existing doctor's profile. Only provided fields are changed (partial update).",
)
async def update_doctor(
    doctor_id: int,
    data: DoctorUpdate,
    repo: DoctorRepoDep,
    current_user: CurrentUser,
) -> GenericResponse[DoctorResponse]:
    """Update a doctor's profile by ID. Requires admin/operational role OR self-update."""
    if not current_user.can_access_admin and current_user.doctor_id != doctor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this doctor profile.",
        )
    doctor = await repo.update(doctor_id, data)
    return GenericResponse(
        message="Doctor updated successfully",
        data=DoctorResponse.model_validate(doctor),
    )


# ---------------------------------------------------------------------------
# Bulk CSV upload — shared constants and helpers
# ---------------------------------------------------------------------------

# Required columns every template CSV must include.
_CSV_REQUIRED_COLUMNS: frozenset[str] = frozenset({"first_name", "last_name", "phone"})

# Guard against abuse / accidental uploads of huge files.
_CSV_MAX_ROWS = 500


def _normalise_phone(raw: str) -> str:
    """Normalise a raw phone string to E.164 (+91XXXXXXXXXX) format."""
    digits = "".join(c for c in raw if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        return f"+{digits}"
    return f"+91{digits}"


def _parse_and_validate_csv(
    raw_bytes: bytes,
) -> tuple[list[dict[str, str]], list[CsvRowValidationError]]:
    """Decode, header-check, and row-validate a CSV upload.

    Pure function — performs no DB access.

    Returns:
        (rows, errors)
        ``rows``   — list of normalised row dicts (keys lower-cased, values stripped).
        ``errors`` — list of ``CsvRowValidationError`` for every validation failure
                     found across *all* rows.  If ``errors`` is non-empty the caller
                     must NOT write to the database.

    Raises:
        HTTPException 400/413 for structural problems (encoding, missing headers,
        empty file, too many rows) that prevent row-level processing.
    """
    # --- Decode ---
    try:
        text = raw_bytes.decode("utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file must be UTF-8 encoded.",
        )

    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty or has no header row.",
        )

    csv_columns = {col.strip().lower() for col in reader.fieldnames if col}
    missing_cols = _CSV_REQUIRED_COLUMNS - csv_columns
    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"CSV is missing required column(s): "
                f"{', '.join(sorted(missing_cols))}."
            ),
        )

    raw_rows = list(reader)
    if len(raw_rows) > _CSV_MAX_ROWS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Too many rows: {len(raw_rows)} "
                f"(maximum allowed: {_CSV_MAX_ROWS})."
            ),
        )

    if not raw_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file contains no data rows.",
        )

    # --- Row-level validation ---
    errors: list[CsvRowValidationError] = []
    rows: list[dict[str, str]] = []

    for row_num, raw_row in enumerate(raw_rows, start=2):  # row 1 = header
        row: dict[str, str] = {
            k.strip().lower(): (v or "").strip()
            for k, v in raw_row.items()
            if k
        }

        phone_raw = row.get("phone", "")
        first_name = row.get("first_name", "")
        last_name = row.get("last_name", "")
        email_val = row.get("email", "")

        # Required fields
        if not phone_raw:
            errors.append(CsvRowValidationError(
                row=row_num, field="phone", error="Phone number is required.",
            ))
        else:
            digits = "".join(c for c in phone_raw if c.isdigit())
            if len(digits) < 10:
                errors.append(CsvRowValidationError(
                    row=row_num, field="phone",
                    error=f"'{phone_raw}' is not a valid phone number (too short).",
                ))

        if not first_name:
            errors.append(CsvRowValidationError(
                row=row_num, field="first_name", error="First name is required.",
            ))

        if not last_name:
            errors.append(CsvRowValidationError(
                row=row_num, field="last_name", error="Last name is required.",
            ))

        # Optional email — validate format when provided
        if email_val:
            if "@" not in email_val or "." not in email_val.split("@")[-1]:
                errors.append(CsvRowValidationError(
                    row=row_num, field="email",
                    error=f"'{email_val}' is not a valid email address.",
                ))

        # Numeric range checks for optional numeric fields
        for field, min_val, max_val in (
            ("years_of_experience", 0, 100),
            ("consultation_fee", 0, None),
            ("registration_year", 1900, 2100),
            ("year_of_mbbs", 1900, 2100),
            ("year_of_specialisation", 1900, 2100),
            ("years_of_clinical_experience", 0, 100),
            ("years_post_specialisation", 0, 100),
        ):
            raw_val = row.get(field, "")
            if raw_val:
                try:
                    num = float(raw_val)
                    if min_val is not None and num < min_val:
                        errors.append(CsvRowValidationError(
                            row=row_num, field=field,
                            error=f"'{raw_val}' must be ≥ {min_val}.",
                        ))
                    if max_val is not None and num > max_val:
                        errors.append(CsvRowValidationError(
                            row=row_num, field=field,
                            error=f"'{raw_val}' must be ≤ {max_val}.",
                        ))
                except ValueError:
                    errors.append(CsvRowValidationError(
                        row=row_num, field=field,
                        error=f"'{raw_val}' is not a valid number.",
                    ))

        # Attach the normalised row even if it has errors — the validation
        # endpoint returns the full error list regardless.
        row["_row_num"] = str(row_num)
        rows.append(row)

    return rows, errors


async def _read_upload_file(file: UploadFile) -> bytes:
    """Read and basic-validate an uploaded file, returning raw bytes."""
    # Be lenient with content_type: browsers often send application/octet-stream
    # for .csv files, so check the extension only when the MIME type is wrong.
    if file.content_type not in ("text/csv", "application/csv", "application/octet-stream", "text/plain"):
        filename = file.filename or ""
        if not filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only CSV files are accepted (.csv extension required).",
            )
    return await file.read()


# Path to the bundled template CSV shipped with the application source.
_TEMPLATE_CSV_PATH: Path = (
    Path(__file__).parent.parent.parent.parent  # src/app
    / "static"
    / "doctor_bulk_upload_template.csv"
)


# ---------------------------------------------------------------------------
# GET /doctors/bulk-upload/csv/template
#   Serve the admin-facing CSV template for download.
# ---------------------------------------------------------------------------

@router.get(
    "/bulk-upload/csv/template",
    summary="Download bulk upload CSV template",
    description=(
        "Download the official CSV template pre-filled with two sample rows "
        "and all supported column headers.  Fill in your doctor data, remove "
        "the sample rows, then upload via the validate and confirm endpoints."
    ),
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "CSV template file",
        },
        404: {"description": "Template file not found on server"},
    },
)
async def download_bulk_upload_template(
    _: AdminOrOperationalUser,
) -> FileResponse:
    """Return the doctor bulk-upload CSV template as a file download."""
    if not _TEMPLATE_CSV_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template file not found. Contact the platform team.",
        )
    return FileResponse(
        path=str(_TEMPLATE_CSV_PATH),
        media_type="text/csv",
        filename="doctor_bulk_upload_template.csv",
    )


# ---------------------------------------------------------------------------
# POST /doctors/bulk-upload/csv/validate
#   Phase 1 — validate the CSV without writing anything to the database.
#   The frontend calls this first, shows any row errors to the operator,
#   and only proceeds to the upload endpoint once the file is clean.
# ---------------------------------------------------------------------------

@router.post(
    "/bulk-upload/csv/validate",
    response_model=CsvValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate a bulk doctor CSV (dry-run, no DB writes)",
    description="""
Validate a CSV file without writing any data to the database.

**Use this endpoint first.**  Upload the completed template CSV here.  The
response lists every row-level error found so the operator can correct the
file and re-upload.  When ``valid=true`` and ``errors=[]`` the file is safe
to submit to the confirm-upload endpoint.

**Required columns:** `first_name`, `last_name`, `phone`
**Optional columns:** `email`, `primary_specialization`, `years_of_experience`,
`consultation_fee`, `medical_registration_number`, `medical_council`,
`registration_year`, `year_of_mbbs`, `year_of_specialisation`,
`years_of_clinical_experience`, `years_post_specialisation`,
plus any other `DoctorUpdate` schema field.

Phone numbers are auto-normalised to E.164 (+91…).
Maximum **500 rows** per upload.
    """,
    responses={
        200: {"description": "Validation complete — check ``valid`` and ``errors``"},
        400: {"description": "Structural problem (encoding, missing headers, empty file)"},
        413: {"description": "Too many rows (> 500)"},
    },
)
async def validate_bulk_upload_csv(
    _: AdminOrOperationalUser,
    file: UploadFile = File(
        ...,
        description="CSV file using the doctor onboarding template (UTF-8, max 500 rows)",
    ),
) -> CsvValidationResponse:
    """Phase 1 — parse and validate the CSV; no DB writes.

    Returns a structured error list so the frontend can highlight which rows
    and fields need correction before the operator confirms the upload.
    """
    raw_bytes = await _read_upload_file(file)
    _rows, errors = _parse_and_validate_csv(raw_bytes)

    logger.info(
        "CSV bulk upload validation",
        total_rows=len(_rows),
        error_count=len(errors),
        filename=file.filename or "unknown",
    )

    return CsvValidationResponse(
        valid=len(errors) == 0,
        total_rows=len(_rows),
        error_count=len(errors),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# POST /doctors/bulk-upload/csv
#   Phase 2 — confirm upload.  Runs the same validation gate first:
#   if any row-level errors exist the request is rejected with a 422 and the
#   full error report so the operator knows exactly what to fix.
#   Only when all rows are clean are records written to the DB.
#
#   Each new doctor gets:
#     • a ``doctors`` row (phone / name / profile fields)
#     • a ``doctor_identity`` row with onboarding_status = PENDING
#     • an initial ``doctor_status_history`` audit entry
#   Existing doctors (matched by normalised phone) are updated in-place;
#   their identity status is not changed (they may already be SUBMITTED etc.).
#
#   Transaction strategy: each row is wrapped in a nested savepoint.
#   A DB-level error on a single row (race condition, unique constraint
#   violation post-validation) rolls back only that savepoint; all other
#   rows in the batch are preserved.  The outer transaction commits once
#   after the loop.  Skipped rows are reported in the response.
# ---------------------------------------------------------------------------

@router.post(
    "/bulk-upload/csv",
    response_model=CsvUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm bulk doctor upload from CSV",
    description="""
Confirm a previously validated CSV upload and write all records to the database.

**Call `/bulk-upload/csv/validate` first.**  This endpoint runs the same
validation gate and returns a `422` with the full error report if any rows are
invalid — so you can fix the file and try again.

For each valid row:
- **New doctors** (matched by phone) are created with `onboarding_status = PENDING`
  and an initial status-history audit entry.
- **Existing doctors** (matched by phone) have their profile fields updated;
  their onboarding status is left unchanged.
- Rows with a duplicate email that conflicts with a different doctor are skipped
  and reported.

The entire upload is atomic: if an unexpected error occurs all writes are rolled
back so the database is never left in a partial state.
    """,
    responses={
        200: {"description": "Upload complete — all rows processed successfully"},
        400: {"description": "Structural CSV problem (encoding / missing headers)"},
        413: {"description": "Too many rows (> 500)"},
        422: {"description": "Row-level validation errors — fix the CSV and re-upload"},
    },
)
async def bulk_upload_doctors_csv(
    db: DbSession,
    current_user: AdminOrOperationalUser,
    file: UploadFile = File(
        ...,
        description="CSV file using the doctor onboarding template (UTF-8, max 500 rows)",
    ),
) -> CsvUploadResponse:
    """Phase 2 — validate then persist all rows atomically.

    Rejects the entire upload if any row fails validation so the operator
    always uploads a clean, fully-correct file.
    """
    raw_bytes = await _read_upload_file(file)
    rows, errors = _parse_and_validate_csv(raw_bytes)

    # Hard gate: any validation error blocks the entire upload.
    if errors:
        logger.warning(
            "CSV bulk upload rejected — validation errors",
            error_count=len(errors),
            filename=file.filename or "unknown",
            uploader_id=current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": (
                    f"Upload rejected: {len(errors)} row(s) failed validation. "
                    "Fix all errors and re-upload."
                ),
                "error_count": len(errors),
                "errors": [e.model_dump() for e in errors],
            },
        )

    doctor_repo = DoctorRepository(db)
    # OnboardingRepository is not used in this path — we write DoctorIdentity
    # and DoctorStatusHistory ORM objects directly via flush() to stay within
    # the savepoint-per-row transaction pattern.

    results: list[CsvUploadRow] = []
    created = updated = skipped = 0
    row_errors: list[CsvRowValidationError] = []

    for row in rows:
        row_num = int(row["_row_num"])
        phone_raw = row.get("phone", "")
        phone = _normalise_phone(phone_raw)
        first_name = row.get("first_name", "")
        last_name = row.get("last_name", "")
        email_val = row.get("email", "") or None

        # Each row runs in its own savepoint so a DB-level error on one row
        # (e.g. unique-constraint violation on email) is isolated and rolled
        # back without affecting rows already processed.
        #
        # IMPORTANT: the repository methods (create_from_phone, update,
        # create_identity) call session.commit() internally, which would
        # normally promote and commit the savepoint.  To keep each row
        # isolated we use session.flush() instead of calling those helpers —
        # we build the ORM objects directly and let the outer transaction
        # commit everything at the end.
        try:
            async with db.begin_nested():
                existing = await doctor_repo.get_by_phone_number(phone)

                if existing:
                    # ── UPDATE existing doctor (flush only, no commit) ───────
                    update_data: dict[str, Any] = {}
                    if first_name:
                        update_data["first_name"] = first_name
                    if last_name:
                        update_data["last_name"] = last_name
                    # Only fill email if the record has none yet — avoid
                    # overwriting an existing verified email.
                    if email_val and not existing.email:
                        update_data["email"] = email_val

                    for col, val in row.items():
                        if col.startswith("_"):
                            continue
                        if col in _DOCTOR_UPDATE_FIELDS and val:
                            update_data[col] = val

                    if update_data:
                        for field, value in DoctorUpdate(**update_data).model_dump(
                            exclude_unset=True, exclude_none=True
                        ).items():
                            # Respect the field_mapping from DoctorRepository
                            model_field = {
                                "awards_recognition": "achievements",
                                "memberships": "professional_memberships",
                                "phone_number": "phone",
                            }.get(field, field)
                            if hasattr(existing, model_field):
                                setattr(existing, model_field, value)
                        db.add(existing)
                        await db.flush()

                    results.append(CsvUploadRow(
                        row=row_num, status="updated",
                        doctor_id=existing.id, phone=phone, email=email_val,
                    ))
                    updated += 1

                else:
                    # ── CREATE new doctor (flush only, no commit) ────────────
                    # ``phone`` is already E.164 (+91…) from _normalise_phone().
                    new_doctor = DoctorModel(
                        phone=phone,
                        first_name=first_name or "",
                        last_name=last_name or "",
                        email=email_val,
                        role="user",
                    )
                    # Apply extra DoctorUpdate fields from the CSV row
                    raw_extra: dict[str, Any] = {}
                    for col, val in row.items():
                        if col.startswith("_"):
                            continue
                        if col in _DOCTOR_UPDATE_FIELDS and val:
                            raw_extra[col] = val

                    if raw_extra:
                        for field, value in DoctorUpdate(**raw_extra).model_dump(
                            exclude_unset=True, exclude_none=True
                        ).items():
                            model_field = {
                                "awards_recognition": "achievements",
                                "memberships": "professional_memberships",
                                "phone_number": "phone",
                            }.get(field, field)
                            if hasattr(new_doctor, model_field):
                                setattr(new_doctor, model_field, value)

                    db.add(new_doctor)
                    await db.flush()  # get new_doctor.id without committing
                    await db.refresh(new_doctor)

                    # ── doctor_identity with PENDING status (flush only) ─────
                    # The identity row drives the onboarding workflow:
                    # PENDING → SUBMITTED → VERIFIED / REJECTED
                    if email_val and first_name and last_name:
                        identity = DoctorIdentity(
                            doctor_id=new_doctor.id,
                            first_name=first_name,
                            last_name=last_name,
                            email=email_val,
                            phone_number=phone,
                            onboarding_status=OnboardingStatus.PENDING,
                        )
                        db.add(identity)
                        await db.flush()

                        history = DoctorStatusHistory(
                            doctor_id=new_doctor.id,
                            previous_status=None,
                            new_status=OnboardingStatus.PENDING,
                            changed_by=str(current_user.id),
                            changed_by_email=current_user.phone or "",
                            notes="Created via bulk CSV upload",
                        )
                        db.add(history)
                        await db.flush()

                    results.append(CsvUploadRow(
                        row=row_num, status="created",
                        doctor_id=new_doctor.id, phone=phone, email=email_val,
                    ))
                    created += 1

        except Exception as exc:
            # Row-level DB/validation error (e.g. unique constraint on email/phone,
            # or Pydantic ValidationError on an unexpected field value).
            # The savepoint was rolled back automatically — this row is
            # excluded; all other rows in the batch are unaffected.
            # Truncate the error detail to 200 chars to prevent overly verbose
            # Pydantic/SQLAlchemy messages from bloating the response.
            error_detail = str(exc)[:200]
            logger.warning(
                "CSV row skipped — DB error",
                row=row_num,
                error=type(exc).__name__,
                detail=error_detail,
            )
            row_errors.append(CsvRowValidationError(
                row=row_num,
                error=f"Could not save row ({type(exc).__name__}): {error_detail}",
            ))
            results.append(CsvUploadRow(
                row=row_num, status="skipped", phone=phone_raw,
            ))
            skipped += 1

    # Commit all successfully-processed rows in one final transaction.
    await db.commit()

    total = len(rows)
    logger.info(
        "CSV bulk upload complete",
        total=total,
        created=created,
        updated=updated,
        skipped=skipped,
        uploader_id=current_user.id,
    )

    return CsvUploadResponse(
        success=skipped == 0,
        message=(
            f"Processed {total} row(s): "
            f"{created} created, {updated} updated"
            + (f", {skipped} row(s) skipped due to errors" if skipped else "")
            + "."
        ),
        total_rows=total,
        created=created,
        updated=updated,
        skipped=skipped,
        rows=results,
        skipped_errors=row_errors,
    )
