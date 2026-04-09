"""
Blog Model for Blog Studio and Comment Moderation.

SQLAlchemy ORM models for the 4-step blog creation process and interactive comments.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    BigInteger,
    String,
    Text,
    func,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.session import Base
from .enums import BlogStatus, CommentAuthorType, CommentStatus

if TYPE_CHECKING:
    from .doctor import Doctor


class Blog(Base):
    """
    Blog entity. Represents a blog post drafted or published by a doctor.
    """

    __tablename__ = "blogs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    subtitle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    opening_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    status: Mapped[str] = mapped_column(
        String(50), 
        nullable=False, 
        default=BlogStatus.DRAFT.value,
        index=True
    )
    
    estimated_read_time: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="In minutes")
    drupal_node_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    seo_schema_markup: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    doctor: Mapped["Doctor"] = relationship(
        "Doctor",
        back_populates="blogs",
        lazy="selectin",
    )
    
    keywords: Mapped[list["BlogKeyword"]] = relationship(
        "BlogKeyword",
        back_populates="blog",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    comments: Mapped[list["BlogComment"]] = relationship(
        "BlogComment",
        back_populates="blog",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class BlogKeyword(Base):
    """Keywords/Tags associated with a blog post."""
    
    __tablename__ = "blog_keywords"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    blog_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keyword: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    blog: Mapped["Blog"] = relationship("Blog", back_populates="keywords")


class BlogComment(Base):
    """Interactive comment from patients or anonymous readers."""
    
    __tablename__ = "blog_comments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    blog_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    drupal_comment_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_type: Mapped[str] = mapped_column(
        String(50), 
        nullable=False, 
        default=CommentAuthorType.PATIENT.value
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    status: Mapped[str] = mapped_column(
        String(50), 
        nullable=False, 
        default=CommentStatus.PENDING.value,
        index=True
    )
    
    ai_insight: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    blog: Mapped["Blog"] = relationship("Blog", back_populates="comments")
