"""Dropdown Options Repository.

Centralised data-access layer for the ``dropdown_options`` table.

Responsibility split vs. OnboardingRepository
----------------------------------------------
``OnboardingRepository`` still owns the legacy ``add_dropdown_values`` /
``get_unique_*`` helpers used by the voice/extraction pipeline.
``DropdownRepository`` is the primary layer for the *dropdown management API*:
public reads (approved only), user submissions (→ PENDING), and admin
approve / reject / CRUD.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.onboarding import DropdownOption, DropdownOptionStatus

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Canonical list of field names exposed via the dropdown API
# ---------------------------------------------------------------------------

SUPPORTED_FIELDS: dict[str, str] = {
    "specialty": "Medical specialisation",
    "sub_specialties": "Sub-specialisation",
    "qualifications": "Academic qualifications / degrees",
    "fellowships": "Fellowship programmes",
    "professional_memberships": "Professional association memberships",
    "languages_spoken": "Languages spoken",
    "age_groups_treated": "Patient age groups",
    "primary_practice_location": "City / practice location",
    "practice_segments": "Practice segment / setting",
    "training_experience": "Notable training & experience",
    "motivation_in_practice": "Motivation in practice",
    "unwinding_after_work": "After-work activities",
    "quality_time_interests": "Personal interests",
    "conditions_treated": "Conditions commonly treated",
    "procedures_performed": "Procedures performed",
}


class DropdownRepository:
    """Async repository for ``dropdown_options`` CRUD + approval workflow."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Public read (approved values only)
    # ------------------------------------------------------------------

    async def list_approved(
        self,
        field_name: str | None = None,
    ) -> list[DropdownOption]:
        """Return all APPROVED dropdown options, optionally for one field.

        Results are sorted by ``display_order`` then ``value`` so the
        frontend receives a stable, human-friendly ordering.
        """
        stmt = (
            select(DropdownOption)
            .where(DropdownOption.status == DropdownOptionStatus.APPROVED)
            .order_by(DropdownOption.display_order, DropdownOption.value)
        )
        if field_name:
            stmt = stmt.where(DropdownOption.field_name == field_name)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_approved_map(self) -> dict[str, list[dict[str, Any]]]:
        """Return a dict mapping every supported field → list of option dicts.

        Only APPROVED options are included.  Useful for the "load all
        dropdowns at once" pattern on first page load.
        """
        rows = await self.list_approved()
        output: dict[str, list[dict[str, Any]]] = {f: [] for f in SUPPORTED_FIELDS}
        for row in rows:
            if row.field_name in output:
                output[row.field_name].append(
                    {
                        "id": row.id,
                        "value": row.value,
                        "label": row.label or row.value,
                        "display_order": row.display_order,
                    }
                )
        return output

    # ------------------------------------------------------------------
    # User / doctor submission (→ PENDING, awaits admin approval)
    # ------------------------------------------------------------------

    async def submit_option(
        self,
        *,
        field_name: str,
        value: str,
        label: str | None = None,
        submitted_by: str | None = None,
        submitted_by_email: str | None = None,
    ) -> DropdownOption:
        """Submit a new dropdown value for admin review.

        - Normalises the value (strip + title-case).
        - Returns the existing row (any status) if the value already exists
          for this field, rather than creating a duplicate.
        - New rows are inserted with ``status = PENDING``, hidden from the
          public dropdown until approved.

        Raises:
            ValueError: If ``field_name`` is not in ``SUPPORTED_FIELDS``.
        """
        if field_name not in SUPPORTED_FIELDS:
            raise ValueError(
                f"Unknown field '{field_name}'. "
                f"Supported fields: {sorted(SUPPORTED_FIELDS)}"
            )

        value = value.strip()
        if not value:
            raise ValueError("Dropdown value must not be blank.")

        # Check for existing entry (case-insensitive match)
        stmt = select(DropdownOption).where(
            and_(
                DropdownOption.field_name == field_name,
                func.lower(DropdownOption.value) == value.lower(),
            )
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            log.info(
                "dropdown_submit_duplicate",
                field_name=field_name,
                value=value,
                existing_status=existing.status,
            )
            return existing

        option = DropdownOption(
            field_name=field_name,
            value=value,
            label=label or value,
            status=DropdownOptionStatus.PENDING,
            is_system=False,
            submitted_by=submitted_by,
            submitted_by_email=submitted_by_email,
        )
        self.session.add(option)
        await self.session.flush()
        await self.session.refresh(option)

        log.info(
            "dropdown_submitted",
            field_name=field_name,
            value=value,
            option_id=option.id,
            submitted_by=submitted_by_email,
        )
        return option

    # ------------------------------------------------------------------
    # Admin read (all statuses, with filtering)
    # ------------------------------------------------------------------

    async def list_all(
        self,
        *,
        field_name: str | None = None,
        status: DropdownOptionStatus | None = None,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
    ) -> tuple[list[DropdownOption], int]:
        """Return options with optional filtering; also returns total count.

        Args:
            field_name: Filter by specific field.
            status:     Filter by approval status.
            skip:       Pagination offset.
            limit:      Page size (max 200).
            search:     Substring match on value or label.

        Returns:
            (rows, total_count)
        """
        limit = min(limit, 200)

        base_where = []
        if field_name:
            base_where.append(DropdownOption.field_name == field_name)
        if status:
            base_where.append(DropdownOption.status == status)
        if search:
            pattern = f"%{search.lower()}%"
            base_where.append(
                or_(
                    func.lower(DropdownOption.value).like(pattern),
                    func.lower(func.coalesce(DropdownOption.label, "")).like(pattern),
                )
            )

        count_stmt = select(func.count(DropdownOption.id))
        if base_where:
            count_stmt = count_stmt.where(and_(*base_where))
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        stmt = (
            select(DropdownOption)
            .order_by(
                DropdownOption.status,
                DropdownOption.field_name,
                DropdownOption.display_order,
                DropdownOption.value,
            )
            .offset(skip)
            .limit(limit)
        )
        if base_where:
            stmt = stmt.where(and_(*base_where))

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_by_id(self, option_id: int) -> DropdownOption | None:
        """Fetch a single option by primary key."""
        result = await self.session.execute(
            select(DropdownOption).where(DropdownOption.id == option_id)
        )
        return result.scalar_one_or_none()

    async def count_pending(self) -> int:
        """Return the number of options awaiting admin review."""
        result = await self.session.execute(
            select(func.count(DropdownOption.id)).where(
                DropdownOption.status == DropdownOptionStatus.PENDING
            )
        )
        return result.scalar() or 0

    # ------------------------------------------------------------------
    # Admin approve / reject
    # ------------------------------------------------------------------

    async def approve(
        self,
        option_id: int,
        *,
        reviewed_by: str | None = None,
        reviewed_by_email: str | None = None,
        review_notes: str | None = None,
    ) -> DropdownOption | None:
        """Approve a PENDING option, making it visible in public dropdowns.

        Returns the updated option, or None if not found.
        """
        option = await self.get_by_id(option_id)
        if option is None:
            return None

        now = datetime.now(UTC)
        option.status = DropdownOptionStatus.APPROVED
        option.reviewed_by = reviewed_by
        option.reviewed_by_email = reviewed_by_email
        option.reviewed_at = now
        option.review_notes = review_notes
        option.updated_at = now

        await self.session.flush()
        await self.session.refresh(option)

        log.info(
            "dropdown_approved",
            option_id=option_id,
            field_name=option.field_name,
            value=option.value,
            reviewed_by=reviewed_by_email,
        )
        return option

    async def reject(
        self,
        option_id: int,
        *,
        reviewed_by: str | None = None,
        reviewed_by_email: str | None = None,
        review_notes: str | None = None,
    ) -> DropdownOption | None:
        """Reject a PENDING option. It will not appear in any dropdown.

        Returns the updated option, or None if not found.
        """
        option = await self.get_by_id(option_id)
        if option is None:
            return None

        now = datetime.now(UTC)
        option.status = DropdownOptionStatus.REJECTED
        option.reviewed_by = reviewed_by
        option.reviewed_by_email = reviewed_by_email
        option.reviewed_at = now
        option.review_notes = review_notes
        option.updated_at = now

        await self.session.flush()
        await self.session.refresh(option)

        log.info(
            "dropdown_rejected",
            option_id=option_id,
            field_name=option.field_name,
            value=option.value,
            reviewed_by=reviewed_by_email,
        )
        return option

    # ------------------------------------------------------------------
    # Admin CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        field_name: str,
        value: str,
        label: str | None = None,
        status: DropdownOptionStatus = DropdownOptionStatus.APPROVED,
        is_system: bool = False,
        display_order: int = 0,
        submitted_by: str | None = None,
        submitted_by_email: str | None = None,
    ) -> DropdownOption:
        """Admin-create a new option (directly APPROVED by default).

        Raises:
            ValueError: If a (field_name, value) duplicate already exists.
        """
        value = value.strip()
        if not value:
            raise ValueError("Dropdown value must not be blank.")

        # Duplicate check
        stmt = select(DropdownOption).where(
            and_(
                DropdownOption.field_name == field_name,
                func.lower(DropdownOption.value) == value.lower(),
            )
        )
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise ValueError(
                f"Value '{value}' already exists for field '{field_name}'."
            )

        option = DropdownOption(
            field_name=field_name,
            value=value,
            label=label or value,
            status=status,
            is_system=is_system,
            display_order=display_order,
            submitted_by=submitted_by,
            submitted_by_email=submitted_by_email,
        )
        self.session.add(option)
        await self.session.flush()
        await self.session.refresh(option)

        log.info(
            "dropdown_created",
            option_id=option.id,
            field_name=field_name,
            value=value,
            status=status,
        )
        return option

    async def update(
        self,
        option_id: int,
        *,
        label: str | None = None,
        display_order: int | None = None,
        review_notes: str | None = None,
    ) -> DropdownOption | None:
        """Update mutable metadata on an existing option.

        Does NOT allow changing ``field_name``, ``value``, or ``status``
        via this method — use ``approve``/``reject`` for status changes.

        Returns the updated option, or None if not found.
        """
        option = await self.get_by_id(option_id)
        if option is None:
            return None

        if label is not None:
            option.label = label
        if display_order is not None:
            option.display_order = display_order
        if review_notes is not None:
            option.review_notes = review_notes
        option.updated_at = datetime.now(UTC)

        await self.session.flush()
        await self.session.refresh(option)
        return option

    async def delete(self, option_id: int) -> bool:
        """Delete a dropdown option.

        System rows (``is_system=True``) cannot be deleted.
        Returns True if deleted, False if not found or protected.
        """
        option = await self.get_by_id(option_id)
        if option is None:
            return False
        if option.is_system:
            log.warning(
                "dropdown_delete_blocked_system_row",
                option_id=option_id,
                field_name=option.field_name,
                value=option.value,
            )
            raise ValueError(
                f"Cannot delete system option (id={option_id}). "
                "System-seeded values are protected. Reject it instead."
            )

        await self.session.delete(option)
        await self.session.flush()
        log.info("dropdown_deleted", option_id=option_id)
        return True

    # ------------------------------------------------------------------
    # Bulk admin operations
    # ------------------------------------------------------------------

    async def bulk_approve(
        self,
        option_ids: list[int],
        *,
        reviewed_by: str | None = None,
        reviewed_by_email: str | None = None,
        review_notes: str | None = None,
    ) -> int:
        """Approve multiple PENDING options in one shot.

        Returns the count of rows actually updated.
        """
        now = datetime.now(UTC)
        stmt = (
            update(DropdownOption)
            .where(
                and_(
                    DropdownOption.id.in_(option_ids),
                    DropdownOption.status == DropdownOptionStatus.PENDING,
                )
            )
            .values(
                status=DropdownOptionStatus.APPROVED,
                reviewed_by=reviewed_by,
                reviewed_by_email=reviewed_by_email,
                reviewed_at=now,
                review_notes=review_notes,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        count = int(getattr(result, "rowcount", 0) or 0)
        log.info(
            "dropdown_bulk_approved",
            count=count,
            reviewed_by=reviewed_by_email,
        )
        return count

    async def bulk_reject(
        self,
        option_ids: list[int],
        *,
        reviewed_by: str | None = None,
        reviewed_by_email: str | None = None,
        review_notes: str | None = None,
    ) -> int:
        """Reject multiple PENDING options in one shot.

        Returns the count of rows actually updated.
        """
        now = datetime.now(UTC)
        stmt = (
            update(DropdownOption)
            .where(
                and_(
                    DropdownOption.id.in_(option_ids),
                    DropdownOption.status == DropdownOptionStatus.PENDING,
                )
            )
            .values(
                status=DropdownOptionStatus.REJECTED,
                reviewed_by=reviewed_by,
                reviewed_by_email=reviewed_by_email,
                reviewed_at=now,
                review_notes=review_notes,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        count = int(getattr(result, "rowcount", 0) or 0)
        log.info(
            "dropdown_bulk_rejected",
            count=count,
            reviewed_by=reviewed_by_email,
        )
        return count
