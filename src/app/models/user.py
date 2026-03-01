"""
User Model for RBAC (Role-Based Access Control).

SQLAlchemy 2.0 ORM model for system users with role management.

Design:
    - Separate from Doctor table: Users can be admins, operational staff, etc.
    - Role-based: ADMIN, OPERATIONAL, USER
    - Soft delete: is_active flag for deactivation without data loss
    - Linked to Doctor: Optional foreign key for doctor-users
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.session import Base
from .enums import UserRole

if TYPE_CHECKING:
    from .doctor import Doctor


class User(Base):
    """
    User entity for authentication and authorization.
    
    This is the central table for RBAC. All authenticated users
    must have a record here to access protected endpoints.
    
    Attributes:
        id: Primary key
        phone: Unique phone number (primary identifier for auth)
        email: Optional email address
        role: User role (admin, operational, user)
        is_active: Soft delete flag (inactive users cannot authenticate)
        doctor_id: Optional link to doctor record (for doctor-users)
        created_at: Record creation timestamp
        updated_at: Record update timestamp
        last_login_at: Last successful authentication
        
    Access Control:
        - ADMIN: Full access to all admin endpoints
        - OPERATIONAL: Limited admin access (configurable)
        - USER: Regular access (no admin endpoints)
        
    Note:
        - A user with is_active=False cannot access any endpoints
        - The phone field is the primary identifier (matches JWT sub)
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identification
    phone: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
        index=True,
        comment="Phone number with country code (e.g., +919988776655)"
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
        comment="Optional email address"
    )

    # Authorization
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.USER.value,
        index=True,
        comment="User role: admin, operational, user"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Active status - inactive users cannot authenticate"
    )

    # Link to doctor (optional - not all users are doctors)
    doctor_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("doctors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional link to doctor record"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful authentication timestamp"
    )

    # Relationship to Doctor
    doctor: Mapped[Doctor | None] = relationship(
        "Doctor",
        back_populates="user",
        lazy="selectin",
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_users_role_active", "role", "is_active"),
        Index("ix_users_phone_active", "phone", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, phone='{self.phone}', role='{self.role}', active={self.is_active})>"

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.role == UserRole.ADMIN.value and self.is_active

    @property
    def is_operational(self) -> bool:
        """Check if user has operational role."""
        return self.role == UserRole.OPERATIONAL.value and self.is_active

    @property
    def can_access_admin(self) -> bool:
        """Check if user can access admin endpoints."""
        return self.is_active and self.role in (UserRole.ADMIN.value, UserRole.OPERATIONAL.value)
