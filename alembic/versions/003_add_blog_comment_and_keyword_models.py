"""Add blog, comment, and keyword models.

Revision ID: 003
Revises: 002
Create Date: 2026-04-15

Merged from three separate migrations:
  - 6adf2ee7c9f8: Add blog and comment models
  - 9efd686a2c4a: Change doctor_id to BigInteger in blogs
  - ab4d661d34d2: Add image_urls to blogs

Creates the ``blogs``, ``blog_comments``, and ``blog_keywords`` tables.
The ``blogs.doctor_id`` column is defined as BIGINT from the start (as
opposed to the original INT that was later altered), and ``image_urls``
(JSON) is included in the initial table definition so that no subsequent
ALTER statements are needed.

Indexes
-------
blogs:
  - ix_blogs_doctor_id
  - ix_blogs_drupal_node_id
  - ix_blogs_status

blog_comments:
  - ix_blog_comments_blog_id
  - ix_blog_comments_drupal_comment_id
  - ix_blog_comments_status

blog_keywords:
  - ix_blog_keywords_blog_id
  - ix_blog_keywords_keyword

Rollback
--------
``downgrade()`` drops all indexes and tables in reverse dependency order.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =======================================================================
    # 1. CREATE blogs TABLE
    #    doctor_id is BIGINT (merged from the follow-up alter-column migration)
    #    image_urls is included here (merged from the follow-up add-column migration)
    # =======================================================================
    op.create_table(
        "blogs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("doctor_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("subtitle", sa.String(length=500), nullable=True),
        sa.Column("opening_quote", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("estimated_read_time", sa.Integer(), nullable=True, comment="In minutes"),
        sa.Column("drupal_node_id", sa.String(length=100), nullable=True),
        sa.Column("seo_schema_markup", sa.JSON(), nullable=True),
        sa.Column("image_urls", sa.JSON(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_blogs_doctor_id"), "blogs", ["doctor_id"], unique=False)
    op.create_index(op.f("ix_blogs_drupal_node_id"), "blogs", ["drupal_node_id"], unique=False)
    op.create_index(op.f("ix_blogs_status"), "blogs", ["status"], unique=False)

    # =======================================================================
    # 2. CREATE blog_comments TABLE
    # =======================================================================
    op.create_table(
        "blog_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("blog_id", sa.Integer(), nullable=False),
        sa.Column("drupal_comment_id", sa.String(length=100), nullable=True),
        sa.Column("author_name", sa.String(length=200), nullable=False),
        sa.Column("author_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("ai_insight", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_blog_comments_blog_id"), "blog_comments", ["blog_id"], unique=False)
    op.create_index(
        op.f("ix_blog_comments_drupal_comment_id"),
        "blog_comments",
        ["drupal_comment_id"],
        unique=False,
    )
    op.create_index(op.f("ix_blog_comments_status"), "blog_comments", ["status"], unique=False)

    # =======================================================================
    # 3. CREATE blog_keywords TABLE
    # =======================================================================
    op.create_table(
        "blog_keywords",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("blog_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["blog_id"], ["blogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_blog_keywords_blog_id"), "blog_keywords", ["blog_id"], unique=False)
    op.create_index(op.f("ix_blog_keywords_keyword"), "blog_keywords", ["keyword"], unique=False)


def downgrade() -> None:
    """Drop indexes and tables in reverse dependency order."""
    # blog_keywords
    op.drop_index(op.f("ix_blog_keywords_keyword"), table_name="blog_keywords")
    op.drop_index(op.f("ix_blog_keywords_blog_id"), table_name="blog_keywords")
    op.drop_table("blog_keywords")

    # blog_comments
    op.drop_index(op.f("ix_blog_comments_status"), table_name="blog_comments")
    op.drop_index(op.f("ix_blog_comments_drupal_comment_id"), table_name="blog_comments")
    op.drop_index(op.f("ix_blog_comments_blog_id"), table_name="blog_comments")
    op.drop_table("blog_comments")

    # blogs
    op.drop_index(op.f("ix_blogs_status"), table_name="blogs")
    op.drop_index(op.f("ix_blogs_drupal_node_id"), table_name="blogs")
    op.drop_index(op.f("ix_blogs_doctor_id"), table_name="blogs")
    op.drop_table("blogs")
