"""Pydantic schemas for the Dropdown Options API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..models.onboarding import DropdownOptionStatus
from ..repositories.dropdown_repository import SUPPORTED_FIELDS

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class DropdownOptionResponse(BaseModel):
    """Full representation of a dropdown option (used in admin views)."""

    id: int
    field_name: str
    value: str
    label: str
    status: DropdownOptionStatus
    is_system: bool
    display_order: int

    # Submission tracking
    submitted_by: str | None = None
    submitted_by_email: str | None = None

    # Review tracking
    reviewed_by: str | None = None
    reviewed_by_email: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DropdownOptionPublic(BaseModel):
    """Minimal representation served on public-facing dropdown endpoints."""

    id: int
    value: str
    label: str
    display_order: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Public read
# ---------------------------------------------------------------------------


class DropdownFieldMeta(BaseModel):
    """Metadata about a single dropdown field."""

    field_name: str
    description: str
    options: list[DropdownOptionPublic]


class AllDropdownsResponse(BaseModel):
    """All supported fields with their approved options."""

    fields: dict[str, DropdownFieldMeta]
    supported_fields: list[str]


# ---------------------------------------------------------------------------
# User / doctor submission
# ---------------------------------------------------------------------------


class DropdownSubmitRequest(BaseModel):
    """Payload for a doctor/user submitting a new dropdown value."""

    field_name: str = Field(
        ...,
        description=f"Target field. Supported: {sorted(SUPPORTED_FIELDS)}",
    )
    value: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="The new option value being proposed.",
    )
    label: str | None = Field(
        default=None,
        max_length=255,
        description="Optional display label (defaults to value).",
    )

    @field_validator("value", "label", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    @field_validator("field_name")
    @classmethod
    def validate_field_name(cls, v: str) -> str:
        if v not in SUPPORTED_FIELDS:
            raise ValueError(
                f"'{v}' is not a supported dropdown field. "
                f"Supported fields: {sorted(SUPPORTED_FIELDS)}"
            )
        return v


class DropdownSubmitResponse(BaseModel):
    """Response after a user submits a new dropdown value."""

    id: int
    field_name: str
    value: str
    label: str
    status: DropdownOptionStatus
    message: str


# ---------------------------------------------------------------------------
# Admin create
# ---------------------------------------------------------------------------


class DropdownCreateRequest(BaseModel):
    """Admin-only: create a new dropdown option (approved immediately)."""

    field_name: str = Field(..., description="Target field name.")
    value: str = Field(..., min_length=1, max_length=255)
    label: str | None = Field(default=None, max_length=255)
    display_order: int = Field(default=0, ge=0)
    is_system: bool = Field(
        default=False,
        description="If true, this row is protected from deletion.",
    )

    @field_validator("value", "label", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


# ---------------------------------------------------------------------------
# Admin update (PATCH)
# ---------------------------------------------------------------------------


class DropdownUpdateRequest(BaseModel):
    """Partial update of a dropdown option's metadata."""

    label: str | None = Field(default=None, max_length=255)
    display_order: int | None = Field(default=None, ge=0)
    review_notes: str | None = Field(default=None, max_length=1000)

    @field_validator("label", mode="before")
    @classmethod
    def strip_label(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


# ---------------------------------------------------------------------------
# Admin approve / reject (single)
# ---------------------------------------------------------------------------


class DropdownReviewRequest(BaseModel):
    """Payload for a single approve or reject action."""

    review_notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional notes stored with the review decision.",
    )


# ---------------------------------------------------------------------------
# Admin bulk approve / reject
# ---------------------------------------------------------------------------


class DropdownBulkReviewRequest(BaseModel):
    """Payload for bulk approve or bulk reject."""

    option_ids: list[int] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="List of dropdown option IDs to approve or reject.",
    )
    review_notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Notes applied to all options in this batch.",
    )


class DropdownBulkReviewResponse(BaseModel):
    """Result of a bulk approve / reject operation."""

    action: Literal["approved", "rejected"]
    updated_count: int
    review_notes: str | None = None


# ---------------------------------------------------------------------------
# Admin list
# ---------------------------------------------------------------------------


class DropdownListResponse(BaseModel):
    """Paginated list of dropdown options for admin view."""

    items: list[DropdownOptionResponse]
    total: int
    skip: int
    limit: int
    pending_count: int = Field(
        description="Total PENDING options across all fields (badge count)."
    )
