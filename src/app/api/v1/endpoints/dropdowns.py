"""
Dropdown Options — Public & Authenticated Endpoints.

PUBLIC  (no auth):
    GET  /dropdowns                 — all approved options for every field
    GET  /dropdowns/{field_name}    — approved options for a single field

AUTHENTICATED (any logged-in user / doctor):
    POST /dropdowns/submit          — propose a new option (→ PENDING, awaits admin review)
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, status

from ....core.rbac import CurrentUser
from ....core.responses import GenericResponse
from ....db.session import DbSession
from ....models.onboarding import DropdownOptionStatus
from ....repositories.dropdown_repository import SUPPORTED_FIELDS, DropdownRepository
from ....schemas.dropdown import (
    AllDropdownsResponse,
    DropdownFieldMeta,
    DropdownOptionPublic,
    DropdownSubmitRequest,
    DropdownSubmitResponse,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/dropdowns")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


async def _build_all_response(repo: DropdownRepository) -> AllDropdownsResponse:
    rows = await repo.list_approved()

    # Group by field_name
    grouped: dict[str, list[DropdownOptionPublic]] = {f: [] for f in SUPPORTED_FIELDS}
    for row in rows:
        if row.field_name in grouped:
            grouped[row.field_name].append(
                DropdownOptionPublic(
                    id=row.id,
                    value=row.value,
                    label=row.label or row.value,
                    display_order=row.display_order,
                )
            )

    fields = {
        field_name: DropdownFieldMeta(
            field_name=field_name,
            description=SUPPORTED_FIELDS[field_name],
            options=options,
        )
        for field_name, options in grouped.items()
    }

    return AllDropdownsResponse(
        fields=fields,
        supported_fields=sorted(SUPPORTED_FIELDS.keys()),
    )


# ---------------------------------------------------------------------------
# GET /dropdowns  — all fields at once (public)
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=GenericResponse[AllDropdownsResponse],
    summary="Get all approved dropdown options (public)",
    description="""
Return every supported dropdown field with its approved options.

**No authentication required.**

This is the recommended endpoint for an initial page load — the frontend
can fetch all dropdowns in a single request and cache them locally.

Each field entry contains:
- `field_name` — the key used when submitting a doctor profile
- `description` — human-readable label for the field
- `options` — list of `{id, value, label, display_order}`

Only **approved** options are returned.  Options in `pending` or `rejected`
state are invisible to end users.
    """,
    tags=["Dropdowns"],
)
async def get_all_dropdowns(
    db: DbSession,
) -> GenericResponse[AllDropdownsResponse]:
    repo = DropdownRepository(db)
    data = await _build_all_response(repo)
    return GenericResponse(
        message="Dropdown options loaded successfully",
        data=data,
    )


# ---------------------------------------------------------------------------
# GET /dropdowns/{field_name}  — single field (public)
# ---------------------------------------------------------------------------


@router.get(
    "/{field_name}",
    response_model=GenericResponse[DropdownFieldMeta],
    summary="Get approved options for a single dropdown field (public)",
    description="""
Return approved options for **one** specific dropdown field.

**No authentication required.**

Use this endpoint when you only need options for a single field
(e.g. to populate a lazy-loaded dropdown or an autocomplete widget).

**Supported `field_name` values:**
- `specialty`
- `sub_specialties`
- `qualifications`
- `fellowships`
- `professional_memberships`
- `languages_spoken`
- `age_groups_treated`
- `primary_practice_location`
- `practice_segments`
- `training_experience`
- `motivation_in_practice`
- `unwinding_after_work`
- `quality_time_interests`
- `conditions_treated`
- `procedures_performed`
    """,
    tags=["Dropdowns"],
)
async def get_dropdown_field(
    field_name: str,
    db: DbSession,
) -> GenericResponse[DropdownFieldMeta]:
    if field_name not in SUPPORTED_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Unknown dropdown field '{field_name}'. "
                f"Supported fields: {sorted(SUPPORTED_FIELDS)}"
            ),
        )

    repo = DropdownRepository(db)
    rows = await repo.list_approved(field_name=field_name)

    options = [
        DropdownOptionPublic(
            id=row.id,
            value=row.value,
            label=row.label or row.value,
            display_order=row.display_order,
        )
        for row in rows
    ]

    return GenericResponse(
        message=f"Options for '{field_name}' loaded successfully",
        data=DropdownFieldMeta(
            field_name=field_name,
            description=SUPPORTED_FIELDS[field_name],
            options=options,
        ),
    )


# ---------------------------------------------------------------------------
# POST /dropdowns/submit  — user submits new option (→ PENDING)
# ---------------------------------------------------------------------------


@router.post(
    "/submit",
    response_model=GenericResponse[DropdownSubmitResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Propose a new dropdown value (authenticated users)",
    description="""
Allow a **logged-in doctor / user** to propose a new value for any
supported dropdown field.

The submitted option is stored with `status = pending` and will **not**
appear in public-facing dropdowns until an Admin or Operational user
approves it via the admin API.

**Behaviour when value already exists:**
- If the value already exists (any status), the existing record is returned
  rather than creating a duplicate.
- The response `status` field reflects the current state of that record.

**Requires:** Any valid JWT (doctor, admin, or operational user).
    """,
    tags=["Dropdowns"],
)
async def submit_dropdown_option(
    payload: DropdownSubmitRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> GenericResponse[DropdownSubmitResponse]:
    repo = DropdownRepository(db)

    try:
        option = await repo.submit_option(
            field_name=payload.field_name,
            value=payload.value,
            label=payload.label,
            submitted_by=str(current_user.id),
            submitted_by_email=getattr(current_user, "email", None),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    await db.commit()

    if option.status == DropdownOptionStatus.APPROVED:
        msg = f"'{payload.value}' already exists and is approved for '{payload.field_name}'."
    elif option.status == DropdownOptionStatus.PENDING:
        msg = (
            f"'{payload.value}' has been submitted for '{payload.field_name}' "
            "and is pending admin review. It will appear in the dropdown once approved."
        )
    else:
        msg = (
            f"'{payload.value}' was previously submitted for '{payload.field_name}' "
            f"and has been {option.status}."
        )

    log.info(
        "dropdown_user_submit",
        field_name=payload.field_name,
        value=payload.value,
        option_id=option.id,
        status=option.status,
        user_id=current_user.id,
    )

    return GenericResponse(
        message=msg,
        data=DropdownSubmitResponse(
            id=option.id,
            field_name=option.field_name,
            value=option.value,
            label=option.label or option.value,
            status=option.status,
            message=msg,
        ),
    )
