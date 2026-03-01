"""
Admin Dropdown Options Endpoints.

All endpoints in this module require Admin or Operational role.

Routes
------
GET    /admin/dropdowns                         — list all options (with filters)
GET    /admin/dropdowns/pending                 — list pending options (badge view)
GET    /admin/dropdowns/{option_id}             — get single option
POST   /admin/dropdowns                         — create option (approved immediately)
PATCH  /admin/dropdowns/{option_id}             — update label / display_order
DELETE /admin/dropdowns/{option_id}             — delete (non-system rows only)
POST   /admin/dropdowns/{option_id}/approve     — approve a PENDING option
POST   /admin/dropdowns/{option_id}/reject      — reject a PENDING option
POST   /admin/dropdowns/bulk-approve            — bulk approve
POST   /admin/dropdowns/bulk-reject             — bulk reject
GET    /admin/dropdowns/fields                  — list all supported field names
"""
from __future__ import annotations
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from ....core.rbac import AdminOrOperationalUser
from ....core.responses import GenericResponse
from ....db.session import DbSession
from ....models.onboarding import DropdownOptionStatus
from ....repositories.dropdown_repository import SUPPORTED_FIELDS, DropdownRepository
from ....schemas.dropdown import (
    DropdownBulkReviewRequest,
    DropdownBulkReviewResponse,
    DropdownCreateRequest,
    DropdownListResponse,
    DropdownOptionResponse,
    DropdownReviewRequest,
    DropdownUpdateRequest,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/dropdowns")


# ---------------------------------------------------------------------------
# Helper: build DropdownOptionResponse from ORM row
# ---------------------------------------------------------------------------

def _to_response(row: object) -> DropdownOptionResponse:
    return DropdownOptionResponse.model_validate(row)


# ---------------------------------------------------------------------------
# GET /admin/dropdowns/fields  — list all supported field names
# ---------------------------------------------------------------------------


@router.get(
    "/fields",
    response_model=GenericResponse[dict[str, Any]],
    summary="List all supported dropdown field names (Admin/Operational)",
    tags=["Admin - Dropdowns"],
)
async def list_supported_fields(
    current_user: AdminOrOperationalUser,
) -> GenericResponse[dict[str, Any]]:
    """Return the canonical list of dropdown field names and their descriptions."""
    return GenericResponse(
        message="Supported dropdown fields",
        data={
            "fields": [
                {"field_name": k, "description": v}
                for k, v in sorted(SUPPORTED_FIELDS.items())
            ]
        },
    )


# ---------------------------------------------------------------------------
# GET /admin/dropdowns  — list all options
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=GenericResponse[DropdownListResponse],
    summary="List all dropdown options with optional filters (Admin/Operational)",
    description="""
Return all dropdown options across all fields, with optional filtering.

**Filter params:**
- `field_name` — filter by specific field
- `status` — filter by `approved`, `pending`, or `rejected`
- `search` — substring match on value or label
- `skip` / `limit` — pagination (max limit: 200)

The response includes a `pending_count` which can be used to display
a badge/counter in the admin UI.
    """,
    tags=["Admin - Dropdowns"],
)
async def list_all_options(
    db: DbSession,
    current_user: AdminOrOperationalUser,
    field_name: str | None = Query(default=None, description="Filter by field name"),
    status_filter: DropdownOptionStatus | None = Query(
        default=None,
        alias="status",
        description="Filter by status: approved | pending | rejected",
    ),
    search: str | None = Query(default=None, description="Substring search on value/label"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> GenericResponse[DropdownListResponse]:
    repo = DropdownRepository(db)

    rows, total = await repo.list_all(
        field_name=field_name,
        status=status_filter,
        search=search,
        skip=skip,
        limit=limit,
    )
    pending_count = await repo.count_pending()

    return GenericResponse(
        message=f"Found {total} option(s)",
        data=DropdownListResponse(
            items=[_to_response(r) for r in rows],
            total=total,
            skip=skip,
            limit=limit,
            pending_count=pending_count,
        ),
    )


# ---------------------------------------------------------------------------
# GET /admin/dropdowns/pending  — pending-only shortcut
# ---------------------------------------------------------------------------


@router.get(
    "/pending",
    response_model=GenericResponse[DropdownListResponse],
    summary="List all PENDING dropdown options awaiting review (Admin/Operational)",
    tags=["Admin - Dropdowns"],
)
async def list_pending_options(
    db: DbSession,
    current_user: AdminOrOperationalUser,
    field_name: str | None = Query(default=None, description="Filter by field name"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> GenericResponse[DropdownListResponse]:
    repo = DropdownRepository(db)

    rows, total = await repo.list_all(
        field_name=field_name,
        status=DropdownOptionStatus.PENDING,
        skip=skip,
        limit=limit,
    )
    pending_count = total  # all rows in this response are pending

    return GenericResponse(
        message=f"{total} option(s) pending review",
        data=DropdownListResponse(
            items=[_to_response(r) for r in rows],
            total=total,
            skip=skip,
            limit=limit,
            pending_count=pending_count,
        ),
    )


# ---------------------------------------------------------------------------
# GET /admin/dropdowns/{option_id}  — single option
# ---------------------------------------------------------------------------


@router.get(
    "/{option_id}",
    response_model=GenericResponse[DropdownOptionResponse],
    summary="Get a single dropdown option by ID (Admin/Operational)",
    tags=["Admin - Dropdowns"],
)
async def get_option(
    option_id: int,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> GenericResponse[DropdownOptionResponse]:
    repo = DropdownRepository(db)
    option = await repo.get_by_id(option_id)
    if option is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dropdown option {option_id} not found.",
        )
    return GenericResponse(
        message="Dropdown option retrieved",
        data=_to_response(option),
    )


# ---------------------------------------------------------------------------
# POST /admin/dropdowns  — create option (approved immediately)
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=GenericResponse[DropdownOptionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new dropdown option (Admin/Operational — approved immediately)",
    tags=["Admin - Dropdowns"],
)
async def create_option(
    payload: DropdownCreateRequest,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> GenericResponse[DropdownOptionResponse]:
    """Create and immediately approve a new dropdown option.

    Useful for admins adding curated / seed values without waiting for
    the user-submission flow.
    """
    repo = DropdownRepository(db)

    try:
        option = await repo.create(
            field_name=payload.field_name,
            value=payload.value,
            label=payload.label,
            status=DropdownOptionStatus.APPROVED,
            is_system=payload.is_system,
            display_order=payload.display_order,
            submitted_by=str(current_user.id),
            submitted_by_email=getattr(current_user, "email", None),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    await db.commit()
    await db.refresh(option)

    log.info(
        "admin_dropdown_created",
        option_id=option.id,
        field_name=option.field_name,
        value=option.value,
        admin_id=current_user.id,
    )

    return GenericResponse(
        message=f"Option '{option.value}' created and approved for '{option.field_name}'",
        data=_to_response(option),
    )


# ---------------------------------------------------------------------------
# PATCH /admin/dropdowns/{option_id}  — update metadata
# ---------------------------------------------------------------------------


@router.patch(
    "/{option_id}",
    response_model=GenericResponse[DropdownOptionResponse],
    summary="Update a dropdown option's label / display order (Admin/Operational)",
    tags=["Admin - Dropdowns"],
)
async def update_option(
    option_id: int,
    payload: DropdownUpdateRequest,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> GenericResponse[DropdownOptionResponse]:
    repo = DropdownRepository(db)
    option = await repo.update(
        option_id,
        label=payload.label,
        display_order=payload.display_order,
        review_notes=payload.review_notes,
    )
    if option is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dropdown option {option_id} not found.",
        )
    await db.commit()
    await db.refresh(option)
    return GenericResponse(
        message="Dropdown option updated",
        data=_to_response(option),
    )


# ---------------------------------------------------------------------------
# DELETE /admin/dropdowns/{option_id}  — delete
# ---------------------------------------------------------------------------


@router.delete(
    "/{option_id}",
    response_model=GenericResponse[dict[str, Any]],
    summary="Delete a dropdown option (Admin/Operational — system rows protected)",
    tags=["Admin - Dropdowns"],
)
async def delete_option(
    option_id: int,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> GenericResponse[dict[str, Any]]:
    """Delete a dropdown option.

    System-seeded rows (`is_system=true`) cannot be deleted — reject them
    to hide them from users, or use PATCH to update their metadata.
    """
    repo = DropdownRepository(db)

    try:
        deleted = await repo.delete(option_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dropdown option {option_id} not found.",
        )

    await db.commit()

    log.info("admin_dropdown_deleted", option_id=option_id, admin_id=current_user.id)

    return GenericResponse(
        message=f"Dropdown option {option_id} deleted successfully",
        data={"option_id": option_id, "deleted": True},
    )


# ---------------------------------------------------------------------------
# POST /admin/dropdowns/{option_id}/approve  — approve single
# ---------------------------------------------------------------------------


@router.post(
    "/{option_id}/approve",
    response_model=GenericResponse[DropdownOptionResponse],
    summary="Approve a PENDING dropdown option (Admin/Operational)",
    description="""
Approve a user-submitted dropdown option.

Once approved, the value becomes immediately visible in the public-facing
`GET /dropdowns/{field_name}` endpoint.
    """,
    tags=["Admin - Dropdowns"],
)
async def approve_option(
    option_id: int,
    payload: DropdownReviewRequest,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> GenericResponse[DropdownOptionResponse]:
    repo = DropdownRepository(db)
    option = await repo.approve(
        option_id,
        reviewed_by=str(current_user.id),
        reviewed_by_email=getattr(current_user, "email", None),
        review_notes=payload.review_notes,
    )
    if option is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dropdown option {option_id} not found.",
        )
    await db.commit()
    await db.refresh(option)

    log.info(
        "admin_dropdown_approved",
        option_id=option_id,
        field_name=option.field_name,
        value=option.value,
        admin_id=current_user.id,
    )

    return GenericResponse(
        message=f"Option '{option.value}' approved for '{option.field_name}'",
        data=_to_response(option),
    )


# ---------------------------------------------------------------------------
# POST /admin/dropdowns/{option_id}/reject  — reject single
# ---------------------------------------------------------------------------


@router.post(
    "/{option_id}/reject",
    response_model=GenericResponse[DropdownOptionResponse],
    summary="Reject a PENDING dropdown option (Admin/Operational)",
    description="""
Reject a user-submitted dropdown option.

Rejected options remain in the database for audit purposes but are
never visible to end users.  You can add `review_notes` to explain
the rejection reason.
    """,
    tags=["Admin - Dropdowns"],
)
async def reject_option(
    option_id: int,
    payload: DropdownReviewRequest,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> GenericResponse[DropdownOptionResponse]:
    repo = DropdownRepository(db)
    option = await repo.reject(
        option_id,
        reviewed_by=str(current_user.id),
        reviewed_by_email=getattr(current_user, "email", None),
        review_notes=payload.review_notes,
    )
    if option is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dropdown option {option_id} not found.",
        )
    await db.commit()
    await db.refresh(option)

    log.info(
        "admin_dropdown_rejected",
        option_id=option_id,
        field_name=option.field_name,
        value=option.value,
        admin_id=current_user.id,
    )

    return GenericResponse(
        message=f"Option '{option.value}' rejected for '{option.field_name}'",
        data=_to_response(option),
    )


# ---------------------------------------------------------------------------
# POST /admin/dropdowns/bulk-approve
# ---------------------------------------------------------------------------


@router.post(
    "/bulk-approve",
    response_model=GenericResponse[DropdownBulkReviewResponse],
    summary="Bulk-approve multiple PENDING options (Admin/Operational)",
    tags=["Admin - Dropdowns"],
)
async def bulk_approve(
    payload: DropdownBulkReviewRequest,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> GenericResponse[DropdownBulkReviewResponse]:
    """Approve multiple pending dropdown options at once (max 200 per request)."""
    repo = DropdownRepository(db)
    count = await repo.bulk_approve(
        payload.option_ids,
        reviewed_by=str(current_user.id),
        reviewed_by_email=getattr(current_user, "email", None),
        review_notes=payload.review_notes,
    )
    await db.commit()

    return GenericResponse(
        message=f"{count} option(s) approved successfully",
        data=DropdownBulkReviewResponse(
            action="approved",
            updated_count=count,
            review_notes=payload.review_notes,
        ),
    )


# ---------------------------------------------------------------------------
# POST /admin/dropdowns/bulk-reject
# ---------------------------------------------------------------------------


@router.post(
    "/bulk-reject",
    response_model=GenericResponse[DropdownBulkReviewResponse],
    summary="Bulk-reject multiple PENDING options (Admin/Operational)",
    tags=["Admin - Dropdowns"],
)
async def bulk_reject(
    payload: DropdownBulkReviewRequest,
    db: DbSession,
    current_user: AdminOrOperationalUser,
) -> GenericResponse[DropdownBulkReviewResponse]:
    """Reject multiple pending dropdown options at once (max 200 per request)."""
    repo = DropdownRepository(db)
    count = await repo.bulk_reject(
        payload.option_ids,
        reviewed_by=str(current_user.id),
        reviewed_by_email=getattr(current_user, "email", None),
        review_notes=payload.review_notes,
    )
    await db.commit()

    return GenericResponse(
        message=f"{count} option(s) rejected successfully",
        data=DropdownBulkReviewResponse(
            action="rejected",
            updated_count=count,
            review_notes=payload.review_notes,
        ),
    )
