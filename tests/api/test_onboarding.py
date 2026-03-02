"""Tests for onboarding endpoints.

Current API surface:
  POST /api/v1/onboarding/extract-resume          — extract data from resume (no auth)
  POST /api/v1/onboarding/submit/{doctor_id}      — doctor self-submits for review (auth)
  GET  /api/v1/onboarding/email-template/{id}     — prefetch email template (admin)
  POST /api/v1/onboarding/verify/{doctor_id}      — admin verifies profile (admin)
  POST /api/v1/onboarding/reject/{doctor_id}      — admin rejects profile (admin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

if TYPE_CHECKING:
    from httpx import AsyncClient

from src.app.models.doctor import Doctor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def seeded_doctor_id(client: AsyncClient, test_engine: "AsyncEngine") -> int:
    """Seed a Doctor row using the same engine used by the ``client`` fixture.

    Both ``client`` and this fixture declare ``test_engine`` as a dependency so
    pytest injects the same engine instance.  We create a separate session from
    that engine, commit the doctor, and the subsequent HTTP requests through
    ``client`` will see the row on the shared in-memory SQLite connection.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        doctor = Doctor(
            email="base.doctor.onboard@example.com",
            phone="+911231231234",
            primary_specialization="General",
            medical_registration_number="REG123",
            medical_council="Medical Council of India",
        )
        session.add(doctor)
        await session.flush()
        doctor_id = doctor.id
        await session.commit()

    assert doctor_id is not None
    return doctor_id


# ---------------------------------------------------------------------------
# POST /api/v1/onboarding/submit/{doctor_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_profile(
    client: AsyncClient, auth_headers: dict[str, str], seeded_doctor_id: int
) -> None:
    """Submitting a doctor profile changes status to 'submitted'."""
    response = await client.post(
        f"/api/v1/onboarding/submit/{seeded_doctor_id}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["new_status"] == "submitted"


# ---------------------------------------------------------------------------
# POST /api/v1/onboarding/verify/{doctor_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_profile(
    client: AsyncClient, auth_headers: dict[str, str], seeded_doctor_id: int
) -> None:
    """Admin verifying a doctor profile changes status to 'verified'."""
    response = await client.post(
        f"/api/v1/onboarding/verify/{seeded_doctor_id}",
        json={"send_email": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["new_status"] == "verified"
    assert "verified_at" in data
    assert data["email_sent"] is False


@pytest.mark.asyncio
async def test_verify_nonexistent_doctor_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Verifying a non-existent doctor returns 404."""
    response = await client.post(
        "/api/v1/onboarding/verify/999999",
        json={"send_email": False},
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/onboarding/reject/{doctor_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_profile(
    client: AsyncClient, auth_headers: dict[str, str], seeded_doctor_id: int
) -> None:
    """Admin rejecting a doctor profile changes status to 'rejected'."""
    response = await client.post(
        f"/api/v1/onboarding/reject/{seeded_doctor_id}",
        json={"reason": "Incomplete information", "send_email": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["new_status"] == "rejected"
    assert data["reason"] == "Incomplete information"
    assert data["email_sent"] is False


@pytest.mark.asyncio
async def test_reject_nonexistent_doctor_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Rejecting a non-existent doctor returns 404."""
    response = await client.post(
        "/api/v1/onboarding/reject/999999",
        json={"reason": "Test", "send_email": False},
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/onboarding/extract-resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_resume(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Resume extraction endpoint returns structured data (mocked)."""
    with patch(
        "src.app.services.extraction_service.ResumeExtractionService.extract_from_file",
        new_callable=AsyncMock,
    ) as mock_extract:
        mock_extract.return_value = (
            {"personal_details": {"email": "john@example.com"}},
            123.4,
        )

        files = {"file": ("resume.pdf", b"dummy content", "application/pdf")}
        response = await client.post(
            "/api/v1/onboarding/extract-resume", files=files, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["personal_details"]["email"] == "john@example.com"


@pytest.mark.asyncio
async def test_extract_resume_invalid_extension(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Uploading an invalid file extension returns 400."""
    files = {"file": ("malicious.exe", b"dummy content", "application/octet-stream")}
    response = await client.post(
        "/api/v1/onboarding/extract-resume", files=files, headers=auth_headers
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/v1/onboarding/email-template/{doctor_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_email_template_nonexistent_doctor_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Getting email template for a non-existent doctor returns 404."""
    response = await client.get(
        "/api/v1/onboarding/email-template/999999?action=verified",
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_requires_auth(client: AsyncClient) -> None:
    """Submit endpoint requires authentication."""
    response = await client.post("/api/v1/onboarding/submit/1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_verify_requires_auth(client: AsyncClient) -> None:
    """Verify endpoint requires authentication."""
    response = await client.post("/api/v1/onboarding/verify/1", json={"send_email": False})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_reject_requires_auth(client: AsyncClient) -> None:
    """Reject endpoint requires authentication."""
    response = await client.post("/api/v1/onboarding/reject/1", json={"reason": "test"})
    assert response.status_code == 401
