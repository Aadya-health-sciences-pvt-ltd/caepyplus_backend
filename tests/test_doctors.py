"""Tests for doctor read/update endpoints.

Current doctor API surface (no POST / DELETE at /api/v1/doctors):
  GET  /api/v1/doctors            — paginated list with optional filters
  GET  /api/v1/doctors/lookup     — full profile lookup by id/email/phone
  GET  /api/v1/doctors/{id}       — single doctor by ID
  PUT  /api/v1/doctors/{id}       — update doctor profile (admin/operational)
  GET  /api/v1/doctors/bulk-upload/csv/template  — CSV template
  POST /api/v1/doctors/bulk-upload/csv/validate  — validate CSV (phase 1)
  POST /api/v1/doctors/bulk-upload/csv           — persist CSV (phase 2)

Doctor creation is done via CSV bulk-upload (or the admin onboarding flow).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from httpx import AsyncClient

from src.app.main import app
from src.app.db.session import get_db
from src.app.models.doctor import Doctor


async def _seed_doctor(client: "AsyncClient") -> int:
    """Insert a Doctor directly via the overridden session and return its id."""
    override_get_db = app.dependency_overrides.get(get_db)
    assert override_get_db is not None

    doctor_id: int | None = None
    gen = override_get_db()
    session: AsyncSession = await gen.__anext__()
    doc = Doctor(
        first_name="John",
        last_name="Smith",
        email="john.smith.doctors@hospital.com",
        phone="+919876540001",
        primary_specialization="Cardiology",
        medical_registration_number="MED-DOCS-001",
        medical_council="Medical Council of India",
        years_of_experience=15,
    )
    session.add(doc)
    await session.flush()
    doctor_id = doc.id
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass

    assert doctor_id is not None
    return doctor_id


# ---------------------------------------------------------------------------
# GET /api/v1/doctors — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_doctors_returns_200(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """GET /doctors returns 200 and a list (possibly empty)."""
    response = await client.get("/api/v1/doctors", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_list_doctors_requires_auth(client: AsyncClient) -> None:
    """GET /doctors without auth returns 401."""
    response = await client.get("/api/v1/doctors")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_doctors_pagination(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Pagination params (page_size) are accepted."""
    response = await client.get("/api/v1/doctors?page_size=2", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) <= 2


# ---------------------------------------------------------------------------
# GET /api/v1/doctors/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_doctor_by_id(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """GET /doctors/{id} returns 200 for an existing doctor."""
    doctor_id = await _seed_doctor(client)
    response = await client.get(f"/api/v1/doctors/{doctor_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["id"] == doctor_id


@pytest.mark.asyncio
async def test_get_doctor_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """GET /doctors/{id} returns 404 for a non-existent doctor."""
    response = await client.get("/api/v1/doctors/99999", headers=auth_headers)
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False


# ---------------------------------------------------------------------------
# PUT /api/v1/doctors/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_doctor(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_update_data: dict,
) -> None:
    """PUT /doctors/{id} updates the doctor and returns 200."""
    doctor_id = await _seed_doctor(client)
    response = await client.put(
        f"/api/v1/doctors/{doctor_id}",
        json=sample_update_data,
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["first_name"] == sample_update_data["first_name"]


@pytest.mark.asyncio
async def test_update_doctor_requires_auth(client: AsyncClient) -> None:
    """PUT /doctors/{id} without auth returns 401."""
    response = await client.put("/api/v1/doctors/1", json={"first_name": "X"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/doctors/bulk-upload/csv/template
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_csv_template_returns_200(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """GET /doctors/bulk-upload/csv/template returns 200 and CSV content."""
    response = await client.get(
        "/api/v1/doctors/bulk-upload/csv/template", headers=auth_headers
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
