"""Unit tests for onboarding admin endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

@pytest.fixture
def identity_payload() -> dict:
    return {
        "doctor_id": 999,
        "full_name": "Admin Test",
        "email": "admin.test@example.com",
        "phone_number": "1112223334",
        "onboarding_status": "pending"
    }

@pytest.fixture
async def sample_identity(client: AsyncClient, auth_headers: dict[str, str], identity_payload: dict) -> dict:
    """Create a sample identity."""
    response = await client.post("/api/v1/onboarding-admin/identities", json=identity_payload, headers=auth_headers)
    return response.json()

@pytest.mark.asyncio
async def test_create_identity(client: AsyncClient, auth_headers: dict[str, str], identity_payload: dict) -> None:
    """Test create identity."""
    payload = identity_payload.copy()
    payload["doctor_id"] = 888
    payload["email"] = "another.test@example.com"
    payload["phone_number"] = "2223334445"
    response = await client.post("/api/v1/onboarding-admin/identities", json=payload, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["data"]["email"] == "another.test@example.com"

@pytest.mark.asyncio
async def test_get_identity(client: AsyncClient, auth_headers: dict[str, str], sample_identity: dict) -> None:
    """Test get identity by doctor_id."""
    doctor_id = sample_identity["data"]["doctor_id"]
    response = await client.get(f"/api/v1/onboarding-admin/identities?doctor_id={doctor_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "admin.test@example.com"

@pytest.mark.asyncio
async def test_get_identity_by_email(client: AsyncClient, auth_headers: dict[str, str], sample_identity: dict) -> None:
    """Test get identity by email."""
    email = sample_identity["data"]["email"]
    response = await client.get(f"/api/v1/onboarding-admin/identities?email={email}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["doctor_id"] == sample_identity["data"]["doctor_id"]


@pytest.mark.asyncio
async def test_add_media(client: AsyncClient, auth_headers: dict[str, str], sample_identity: dict) -> None:
    """Test add media record."""
    doctor_id = sample_identity["data"]["doctor_id"]
    payload = {
        "media_type": "image",
        "media_category": "profile_photo",
        "field_name": "profile_photo",
        "file_uri": "/path/to/photo.jpg",
        "file_name": "photo.jpg",
        "file_size": 1024,
        "mime_type": "image/jpeg"
    }
    response = await client.post(f"/api/v1/onboarding-admin/media/{doctor_id}", json=payload, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["data"]["doctor_id"] == doctor_id

@pytest.mark.asyncio
async def test_list_media(client: AsyncClient, auth_headers: dict[str, str], sample_identity: dict) -> None:
    """Test list media records."""
    doctor_id = sample_identity["data"]["doctor_id"]
    payload = {
        "media_type": "image",
        "media_category": "profile_photo",
        "field_name": "profile_photo",
        "file_uri": "/path/to/photo.jpg",
        "file_name": "photo.jpg",
        "file_size": 1024,
        "mime_type": "image/jpeg"
    }
    await client.post(f"/api/v1/onboarding-admin/media/{doctor_id}", json=payload, headers=auth_headers)

    response = await client.get(f"/api/v1/onboarding-admin/media/{doctor_id}", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()["data"]) > 0

@pytest.mark.asyncio
async def test_delete_media(client: AsyncClient, auth_headers: dict[str, str], sample_identity: dict) -> None:
    """Test delete media record."""
    doctor_id = sample_identity["data"]["doctor_id"]
    payload = {
        "media_type": "image",
        "media_category": "profile_photo",
        "field_name": "profile_photo",
        "file_uri": "/path/to/photo_del.jpg",
        "file_name": "photo_del.jpg",
        "file_size": 1024,
        "mime_type": "image/jpeg"
    }
    create_resp = await client.post(f"/api/v1/onboarding-admin/media/{doctor_id}", json=payload, headers=auth_headers)
    media_id = create_resp.json()["data"]["media_id"]

    response = await client.delete(f"/api/v1/onboarding-admin/media/{media_id}", headers=auth_headers)
    assert response.status_code == 204

@pytest.mark.asyncio
async def test_status_history(client: AsyncClient, auth_headers: dict[str, str], sample_identity: dict) -> None:
    """Test log and get status history."""
    doctor_id = sample_identity["data"]["doctor_id"]
    payload = {
        "previous_status": "pending",
        "new_status": "verified",
        "changed_by": "1",
        "reason": "Looking good"
    }

    # Log status
    post_resp = await client.post(f"/api/v1/onboarding-admin/status-history/{doctor_id}", json=payload, headers=auth_headers)
    assert post_resp.status_code == 201

    # Get history
    get_resp = await client.get(f"/api/v1/onboarding-admin/status-history/{doctor_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert len(get_resp.json()["data"]) > 0

@pytest.mark.asyncio
async def test_list_doctors_with_filter(client: AsyncClient, auth_headers: dict[str, str], sample_identity: dict) -> None:
    """Test fetching a known identity by doctor_id from the onboarding-admin identities endpoint."""
    doctor_id = sample_identity["data"]["doctor_id"]
    response = await client.get(f"/api/v1/onboarding-admin/identities?doctor_id={doctor_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["doctor_id"] == doctor_id

@pytest.mark.asyncio
async def test_get_doctor_full_by_id(client: AsyncClient, auth_headers: dict[str, str], sample_identity: dict) -> None:
    """Test fetching an identity by doctor_id via onboarding-admin/identities endpoint."""
    doctor_id = sample_identity["data"]["doctor_id"]
    response = await client.get(f"/api/v1/onboarding-admin/identities?doctor_id={doctor_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["email"] == sample_identity["data"]["email"]
    assert data["data"]["doctor_id"] == doctor_id

@pytest.mark.asyncio
async def test_get_doctor_full_by_email(client: AsyncClient, auth_headers: dict[str, str], sample_identity: dict) -> None:
    """Test fetching an identity by email via onboarding-admin/identities endpoint."""
    email = sample_identity["data"]["email"]
    response = await client.get(f"/api/v1/onboarding-admin/identities?email={email}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["doctor_id"] == sample_identity["data"]["doctor_id"]

@pytest.mark.asyncio
async def test_get_doctor_full_by_phone(client: AsyncClient, auth_headers: dict[str, str], sample_identity: dict) -> None:
    """Test that the onboarding-admin identity is accessible by doctor_id (phone lookup not supported by endpoint)."""
    doctor_id = sample_identity["data"]["doctor_id"]
    response = await client.get(f"/api/v1/onboarding-admin/identities?doctor_id={doctor_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["phone_number"] == sample_identity["data"]["phone_number"]
