"""Unit tests for admin users endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

@pytest.mark.asyncio
async def test_seed_admin_user(client: AsyncClient) -> None:
    """Test seeding initial admin user."""
    payload = {
        "phone": "+919999999999",
        "email": "seed_admin@example.com",
        "role": "admin",
        "is_active": True
    }
    response = await client.post("/api/v1/admin/users/seed", json=payload)
    # Since conftest.py pre-seeds an admin user via autouse fixture,
    # the seed endpoint will be disabled and return 403.
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_list_users(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test listing users."""
    response = await client.get("/api/v1/admin/users", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "users" in data["data"]

@pytest.mark.asyncio
async def test_create_user(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test creating a new user by admin."""
    payload = {
        "phone": "+1234567890",
        "email": "newuser@example.com",
        "role": "user",
        "is_active": True
    }
    response = await client.post("/api/v1/admin/users", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["success"] is True

@pytest.mark.asyncio
async def test_get_user(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test getting a user by ID."""
    # First create a user
    payload = {"phone": "+1987654321", "email": "getme@example.com", "role": "user"}
    create_resp = await client.post("/api/v1/admin/users", json=payload, headers=auth_headers)
    assert create_resp.status_code == 201
    user_id = create_resp.json()["data"]["user"]["id"]

    response = await client.get(f"/api/v1/admin/users/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["id"] == user_id

@pytest.mark.asyncio
async def test_list_admins(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test listing admins."""
    response = await client.get("/api/v1/admin/users/admins", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    # It uses GenericResponse[UserListResponse]
    assert "users" in data["data"]
    assert all(u["role"] == "admin" for u in data["data"]["users"])

@pytest.mark.asyncio
async def test_update_user(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test updating user."""
    create_resp = await client.post("/api/v1/admin/users", json={"phone": "+1122334455", "role": "user"}, headers=auth_headers)
    user_id = create_resp.json()["data"]["user"]["id"]

    response = await client.patch(f"/api/v1/admin/users/{user_id}", json={"doctor_id": 99}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["user"]["doctor_id"] == 99

@pytest.mark.asyncio
async def test_update_user_role(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test updating user role."""
    create_resp = await client.post("/api/v1/admin/users", json={"phone": "+5544332211", "role": "user"}, headers=auth_headers)
    user_id = create_resp.json()["data"]["user"]["id"]

    response = await client.patch(f"/api/v1/admin/users/{user_id}/role", json={"role": "operational"}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["user"]["role"] == "operational"

@pytest.mark.asyncio
async def test_update_user_status(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test updating user status."""
    create_resp = await client.post("/api/v1/admin/users", json={"phone": "+9988776655", "role": "user"}, headers=auth_headers)
    user_id = create_resp.json()["data"]["user"]["id"]

    response = await client.patch(f"/api/v1/admin/users/{user_id}/status", json={"is_active": False}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["user"]["is_active"] is False

@pytest.mark.asyncio
async def test_deactivate_user(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test soft deleting a user."""
    create_resp = await client.post("/api/v1/admin/users", json={"phone": "+7777777777", "role": "user"}, headers=auth_headers)
    user_id = create_resp.json()["data"]["user"]["id"]

    response = await client.delete(f"/api/v1/admin/users/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["success"] is True
