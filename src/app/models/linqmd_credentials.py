"""LinQMD credentials stored after successful admin profile creation."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db.session import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class DoctorLinqmdCredentials(Base):
    """One LinQMD profile per doctor (admin-created via Practice Hub sync).

    Passwords are stored as returned by LinQMD for admin retrieval only;
    access is restricted to admin/operation roles via API.
    """

    __tablename__ = "doctor_linqmd_credentials"
    __table_args__ = (UniqueConstraint("doctor_id", name="uq_doctor_linqmd_credentials_doctor_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doctor_name: Mapped[str] = mapped_column(Text, nullable=False)
    linqmd_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    linqmd_username: Mapped[str] = mapped_column(String(255), nullable=False)
    linqmd_password: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
