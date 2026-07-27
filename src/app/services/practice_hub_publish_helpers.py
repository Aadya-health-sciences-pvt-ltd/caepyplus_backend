"""Shared blog lookup by doctor with diagnostic logging (Blog Studio + Practice Hub)."""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.blog import Blog

logger = logging.getLogger(__name__)


async def get_owned_blog(
    db: AsyncSession,
    *,
    blog_id: int,
    doctor_id: int,
    route: str,
    log_prefix: str = "blog_access",
) -> Blog:
    """Load blog when ``blog_id`` belongs to ``doctor_id``; log diagnostics on 404."""
    logger.info(
        "%s start route=%s blog_id=%s doctor_id=%s",
        log_prefix,
        route,
        blog_id,
        doctor_id,
    )

    result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.doctor_id == doctor_id)
    )
    blog = result.scalar_one_or_none()
    if blog is not None:
        logger.info(
            "%s found route=%s blog_id=%s doctor_id=%s status=%s title=%r",
            log_prefix,
            route,
            blog.id,
            blog.doctor_id,
            blog.status,
            (blog.title or "")[:80],
        )
        return blog

    by_id = await db.execute(select(Blog).where(Blog.id == blog_id))
    blog_row = by_id.scalar_one_or_none()
    if blog_row is None:
        doctor_blog_count = await db.scalar(
            select(func.count()).select_from(Blog).where(Blog.doctor_id == doctor_id)
        )
        logger.warning(
            "%s not_found route=%s blog_id=%s doctor_id=%s "
            "reason=no_row_with_blog_id doctor_blog_count=%s",
            log_prefix,
            route,
            blog_id,
            doctor_id,
            doctor_blog_count or 0,
        )
    else:
        logger.warning(
            "%s not_found route=%s blog_id=%s doctor_id=%s "
            "reason=doctor_mismatch actual_doctor_id=%s actual_status=%s",
            log_prefix,
            route,
            blog_id,
            doctor_id,
            blog_row.doctor_id,
            blog_row.status,
        )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")


async def get_blog_for_practice_hub_publish(
    db: AsyncSession,
    *,
    blog_id: int,
    doctor_id: int,
    route: str,
) -> Blog:
    """Load blog for Practice Hub publish (same lookup as ``get_owned_blog``)."""
    return await get_owned_blog(
        db,
        blog_id=blog_id,
        doctor_id=doctor_id,
        route=route,
        log_prefix="practice_hub_publish",
    )
