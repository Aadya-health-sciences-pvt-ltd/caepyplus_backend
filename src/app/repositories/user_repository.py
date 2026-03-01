"""User Repository - Data access layer for RBAC users."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import UserRole
from ..models.user import User

log = structlog.get_logger(__name__)


class UserRepository:
    """Repository for User CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with database session."""
        self.session = session

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    async def get_by_id(self, user_id: int) -> User | None:
        """Get user by ID."""
        query = select(User).where(User.id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        """Get user by phone number (normalized with +91 prefix)."""
        normalized = self._normalize_phone(phone)
        query = select(User).where(User.phone == normalized)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email address."""
        query = select(User).where(User.email == email.lower())
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_active_by_phone(self, phone: str) -> User | None:
        """Get active user by phone number."""
        normalized = self._normalize_phone(phone)
        query = select(User).where(
            and_(
                User.phone == normalized,
                User.is_active.is_(True),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        role: str | list[str] | None = None,
        is_active: bool | None = None,
    ) -> Sequence[User]:
        """Get all users with optional filtering."""
        query = select(User)

        if role:
            if isinstance(role, list):
                query = query.where(User.role.in_(role))
            else:
                query = query.where(User.role == role)
        if is_active is not None:
            query = query.where(User.is_active == is_active)

        query = query.offset(skip).limit(limit).order_by(User.created_at.desc())
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_admins(self, active_only: bool = True) -> Sequence[User]:
        """Get all admin users."""
        query = select(User).where(User.role == UserRole.ADMIN.value)
        if active_only:
            query = query.where(User.is_active.is_(True))
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_all(
        self,
        role: str | list[str] | None = None,
        is_active: bool | None = None,
    ) -> int:
        """Count total users matching the same filters as get_all."""
        query = select(func.count(User.id))

        if role:
            if isinstance(role, list):
                query = query.where(User.role.in_(role))
            else:
                query = query.where(User.role == role)
        if is_active is not None:
            query = query.where(User.is_active.is_(is_active))

        result = await self.session.execute(query)
        return result.scalar_one()

    # =========================================================================
    # CREATE OPERATIONS
    # =========================================================================

    async def create(
        self,
        phone: str | None,
        email: str | None = None,
        role: str = UserRole.USER.value,
        is_active: bool = True,
        doctor_id: int | None = None,
    ) -> User:
        """Create a new user."""
        normalized_phone = self._normalize_phone(phone)

        user = User(
            phone=normalized_phone,
            email=email.lower() if email else None,
            role=role,
            is_active=is_active,
            doctor_id=doctor_id,
        )

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        log.info("user_created", user_id=user.id, role=role)
        return user

    async def create_from_doctor(
        self,
        doctor_id: int,
        phone: str | None,
        email: str | None = None,
        role: str = UserRole.USER.value,
    ) -> User:
        """Create a user linked to an existing doctor."""
        return await self.create(
            phone=phone,
            email=email,
            role=role,
            is_active=True,
            doctor_id=doctor_id,
        )

    async def get_or_create(
        self,
        phone: str | None,
        email: str | None = None,
        doctor_id: int | None = None,
    ) -> tuple[User, bool]:
        """
        Get existing user or create new one.
        
        Returns:
            Tuple of (user, is_new) where is_new is True if created
        """
        if phone:
            existing = await self.get_by_phone(phone)
            if existing:
                return existing, False
        elif email:
            existing = await self.get_by_email(email)
            if existing:
                return existing, False
        else:
            raise ValueError("Must provide either phone or email to get_or_create")

        new_user = await self.create(
            phone=phone,
            email=email,
            role=UserRole.USER.value,
            is_active=True,
            doctor_id=doctor_id,
        )
        return new_user, True

    # =========================================================================
    # UPDATE OPERATIONS
    # =========================================================================

    async def update_fields(
        self,
        user_id: int,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        doctor_id: int | None = None,
    ) -> User | None:
        """Apply one or more field updates to a user in a single transaction.

        Use this instead of chaining ``update_role`` / ``set_active`` /
        ``link_doctor`` separately, which would issue multiple sequential
        commits and leave the row in a partially-updated state if any step
        fails after the first commit.

        Returns the refreshed User or None if not found.
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None

        now = datetime.now(UTC)
        if role is not None:
            old_role = user.role
            user.role = role
            log.info("user_role_staged", user_id=user_id, old_role=old_role, new_role=role)
        if is_active is not None:
            user.is_active = is_active
            log.info("user_active_staged", user_id=user_id, is_active=is_active)
        if doctor_id is not None:
            user.doctor_id = doctor_id
            log.info("user_doctor_linked_staged", user_id=user_id, doctor_id=doctor_id)
        user.updated_at = now

        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_role(self, user_id: int, role: str) -> User | None:
        """Update user's role."""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        old_role = user.role
        user.role = role
        user.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(user)

        log.info("user_role_updated", user_id=user_id, old_role=old_role, new_role=role)
        return user

    async def set_active(self, user_id: int, is_active: bool) -> User | None:
        """Activate or deactivate a user."""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.is_active = is_active
        user.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(user)

        action = "user_activated" if is_active else "user_deactivated"
        log.info(action, user_id=user_id)
        return user

    async def deactivate(self, user_id: int) -> User | None:
        """Deactivate a user (soft delete)."""
        return await self.set_active(user_id, False)

    async def activate(self, user_id: int) -> User | None:
        """Activate a user."""
        return await self.set_active(user_id, True)

    async def update_last_login(self, user_id: int) -> None:
        """Update user's last login timestamp."""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def link_doctor(self, user_id: int, doctor_id: int) -> User | None:
        """Link a user to a doctor record."""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.doctor_id = doctor_id
        user.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(user)

        log.info("user_doctor_linked", user_id=user_id, doctor_id=doctor_id)
        return user

    # =========================================================================
    # DELETE OPERATIONS
    # =========================================================================

    async def delete(self, user_id: int) -> bool:
        """Hard delete a user (use deactivate for soft delete)."""
        user = await self.get_by_id(user_id)
        if not user:
            return False

        await self.session.delete(user)
        await self.session.commit()

        log.info("user_deleted", user_id=user_id)
        return True

    # =========================================================================
    # AUTHORIZATION HELPERS
    # =========================================================================

    async def is_admin(self, phone: str) -> bool:
        """Check if user with phone is an active admin."""
        user = await self.get_active_by_phone(phone)
        return user is not None and user.role == UserRole.ADMIN.value

    async def can_access_admin(self, phone: str) -> bool:
        """Check if user can access admin endpoints (admin or operational)."""
        user = await self.get_active_by_phone(phone)
        if not user:
            return False
        return user.role in (UserRole.ADMIN.value, UserRole.OPERATIONAL.value)

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _normalize_phone(self, phone: str | None) -> str | None:
        """Normalize an Indian mobile phone number to E.164 (+91XXXXXXXXXX) format.

        Handles these common input variants:
          +919988776655   → +919988776655  (already E.164, returned as-is)
          919988776655    → +919988776655  (91-prefixed without +)
          9988776655      → +919988776655  (bare 10-digit Indian number)
          09988776655     → +919988776655  (leading 0, domestic format)

        Numbers already starting with '+' are returned unchanged so that
        non-Indian numbers (e.g. +1-555-0123) pass through correctly and
        can be looked up by their stored value.
        """
        if not phone:
            return phone

        stripped = phone.strip()
        if not stripped:
            return stripped

        # If the caller already supplied a properly formatted E.164 number, trust it.
        if stripped.startswith("+"):
            return stripped

        digits_only = "".join(c for c in stripped if c.isdigit())

        if digits_only.startswith("91") and len(digits_only) == 12:
            # e.g. 919988776655
            return "+" + digits_only
        if digits_only.startswith("0") and len(digits_only) == 11:
            # e.g. 09988776655 → strip leading 0, add +91
            return "+91" + digits_only[1:]
        if len(digits_only) == 10:
            # Bare 10-digit Indian number
            return "+91" + digits_only
        # Unrecognised format — store as-is to avoid silent corruption
        return stripped
