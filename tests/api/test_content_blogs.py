"""Tests for content creator blog routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from httpx import AsyncClient

from src.app.models.doctor import Doctor


@pytest.fixture
async def verified_doctor_id(test_engine: AsyncEngine) -> int:
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        doctor = Doctor(
            email="verified.content@example.com",
            phone="+919900000001",
            primary_specialization="Cardiology",
            medical_registration_number="REG-CC-1",
            medical_council="Medical Council of India",
            onboarding_status="verified",
        )
        session.add(doctor)
        await session.flush()
        doctor_id = doctor.id
        await session.commit()
    assert doctor_id is not None
    return doctor_id


@pytest.fixture
async def pending_doctor_id(test_engine: AsyncEngine) -> int:
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        doctor = Doctor(
            email="pending.content@example.com",
            phone="+919900000002",
            primary_specialization="General",
            medical_registration_number="REG-CC-2",
            medical_council="Medical Council of India",
            onboarding_status="pending",
        )
        session.add(doctor)
        await session.flush()
        doctor_id = doctor.id
        await session.commit()
    assert doctor_id is not None
    return doctor_id


@pytest.mark.asyncio
async def test_content_list_blogs_verified_doctor(
    client: AsyncClient,
    content_creator_headers: dict[str, str],
    verified_doctor_id: int,
) -> None:
    response = await client.get(
        f"/api/v1/content/doctors/{verified_doctor_id}/blogs",
        headers=content_creator_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


@pytest.mark.asyncio
async def test_content_list_blogs_admin_forbidden(
    client: AsyncClient,
    auth_headers: dict[str, str],
    verified_doctor_id: int,
) -> None:
    response = await client.get(
        f"/api/v1/content/doctors/{verified_doctor_id}/blogs",
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_content_list_blogs_unverified_doctor_forbidden(
    client: AsyncClient,
    content_creator_headers: dict[str, str],
    pending_doctor_id: int,
) -> None:
    response = await client.get(
        f"/api/v1/content/doctors/{pending_doctor_id}/blogs",
        headers=content_creator_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_content_list_blogs_unknown_doctor_not_found(
    client: AsyncClient,
    content_creator_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/content/doctors/999999/blogs",
        headers=content_creator_headers,
    )
    assert response.status_code == 404
