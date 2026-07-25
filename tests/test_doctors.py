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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from httpx import AsyncClient

from tests.conftest import _create_test_jwt

from src.app.main import app
from src.app.db.session import get_db
from src.app.core.doctor_utils import is_synthetic_identity_email
from src.app.models.doctor import Doctor
from src.app.models.enums import UserRole
from src.app.models.onboarding import DoctorIdentity, DoctorMedia
from src.app.models.user import User
from src.app.repositories.doctor_repository import DoctorRepository


async def _seed_doctor(client: "AsyncClient") -> int:
    """Insert a Doctor directly via the overridden session and return its id."""
    override_get_db = app.dependency_overrides.get(get_db)
    assert override_get_db is not None

    doctor_id: int | None = None
    gen = override_get_db()
    session: AsyncSession = await gen.__anext__()
    doc = Doctor(
        full_name="John Smith",
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
    assert data["data"]["full_name"] == sample_update_data["full_name"]


@pytest.mark.asyncio
async def test_update_doctor_requires_auth(client: AsyncClient) -> None:
    """PUT /doctors/{id} without auth returns 401."""
    response = await client.put("/api/v1/doctors/1", json={"full_name": "X"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/doctors/{id}/profile-photo
# ---------------------------------------------------------------------------


async def _seed_phone_only_doctor(client: "AsyncClient") -> tuple[int, str]:
    """Create OTP-style doctor (phone, no email) and return (id, phone)."""
    override_get_db = app.dependency_overrides.get(get_db)
    assert override_get_db is not None

    doctor_id: int | None = None
    phone = "+919876543288"
    gen = override_get_db()
    session: AsyncSession = await gen.__anext__()
    doc_repo = DoctorRepository(session)
    doctor = await doc_repo.create_from_phone(phone)
    doctor_id = doctor.id
    session.add(
        User(
            phone=phone,
            email=None,
            role=UserRole.USER.value,
            is_active=True,
            doctor_id=doctor_id,
        )
    )
    await session.flush()
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass

    assert doctor_id is not None
    return doctor_id, phone


@pytest.mark.asyncio
async def test_upload_profile_photo_bootstraps_identity_for_phone_only_doctor(
    client: AsyncClient,
    mock_blob_storage: MagicMock,
) -> None:
    """Early onboarding: photo upload before form fields creates identity + media."""
    doctor_id, phone = await _seed_phone_only_doctor(client)
    token = _create_test_jwt(
        subject=phone,
        doctor_id=doctor_id,
        email=None,
        role="user",
    )
    headers = {"Authorization": f"Bearer {token}"}

    mock_upload = MagicMock(
        success=True,
        blob_id="test_blob",
        file_uri=f"doctors/{doctor_id}/profile_photo/test.jpg",
        file_size=128,
        mime_type="image/jpeg",
        content_hash="abc",
        error_message=None,
    )
    mock_blob_storage.upload_from_bytes = AsyncMock(return_value=mock_upload)

    with patch(
        "src.app.api.v1.endpoints.doctors.get_blob_storage_service",
        return_value=mock_blob_storage,
    ):
        response = await client.post(
            f"/api/v1/doctors/{doctor_id}/profile-photo",
            headers=headers,
            files={"file": ("profile-photo.jpg", b"\xff\xd8\xff", "image/jpeg")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["profile_photo"] == mock_upload.file_uri

    override_get_db = app.dependency_overrides.get(get_db)
    assert override_get_db is not None
    gen = override_get_db()
    session: AsyncSession = await gen.__anext__()
    identity = (
        await session.execute(
            select(DoctorIdentity).where(DoctorIdentity.doctor_id == doctor_id)
        )
    ).scalar_one_or_none()
    media_rows = (
        await session.execute(
            select(DoctorMedia).where(DoctorMedia.doctor_id == doctor_id)
        )
    ).scalars().all()
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass

    assert identity is not None
    assert is_synthetic_identity_email(identity.email)
    assert identity.phone_number == phone
    assert len(media_rows) == 1
    assert media_rows[0].field_name == "profile_photo"


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
    assert "full_name" in response.text
    assert "practice_location" in response.text
    assert "practice_location_1" not in next(
        ln for ln in response.text.splitlines() if ln.startswith("phone,")
    )
    assert "first_name,last_name" not in response.text.splitlines()[0]
    header_line = next(
        (ln for ln in response.text.splitlines() if ln.startswith("phone,")),
        "",
    )
    assert header_line.startswith("phone,email,full_name")
    assert ",theme" in header_line


@pytest.mark.asyncio
async def test_bulk_csv_validate_core_sample(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Phase 1 validate accepts a minimal core-template CSV row."""
    csv_body = (
        "phone,email,full_name,specialty,city,languages,medical_registration_number,"
        "medical_council,year_of_mbbs\n"
        "9876500011,core.upload@example.com,Dr. Core Upload,Cardiology,Bangalore,"
        "English|Hindi,REG-CORE-1,Karnataka Medical Council,2012\n"
    )
    response = await client.post(
        "/api/v1/doctors/bulk-upload/csv/validate",
        headers=auth_headers,
        files={"file": ("core.csv", csv_body.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["error_count"] == 0


@pytest.mark.asyncio
async def test_bulk_csv_validate_rejects_missing_specialty(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    csv_body = (
        "phone,email,full_name,medical_registration_number,medical_council\n"
        "9876500022,bad@example.com,Dr. No Specialty,REG1,Council\n"
    )
    response = await client.post(
        "/api/v1/doctors/bulk-upload/csv/validate",
        headers=auth_headers,
        files={"file": ("bad.csv", csv_body.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any(e["field"] == "specialty" for e in data["errors"])
