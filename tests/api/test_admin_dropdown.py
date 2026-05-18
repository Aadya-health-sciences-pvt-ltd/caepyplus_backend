"""Tests for admin dropdown endpoints — /api/v1/admin/dropdowns/*."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


# ---------------------------------------------------------------------------
# GET /admin/dropdowns/fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_supported_fields(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can list all supported dropdown field names."""
    response = await client.get("/api/v1/admin/dropdowns/fields", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "data" in data
    fields = data["data"]["fields"]
    assert isinstance(fields, list)
    assert len(fields) > 0
    # Each entry has field_name and description
    first = fields[0]
    assert "field_name" in first
    assert "description" in first


@pytest.mark.asyncio
async def test_list_supported_fields_requires_auth(client: AsyncClient) -> None:
    """Fields endpoint requires authentication."""
    response = await client.get("/api/v1/admin/dropdowns/fields")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /admin/dropdowns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_all_options(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can list all dropdown options with pagination."""
    response = await client.get("/api/v1/admin/dropdowns", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "data" in data
    payload = data["data"]
    assert "items" in payload
    assert "total" in payload
    assert "skip" in payload
    assert "limit" in payload
    assert "pending_count" in payload
    assert isinstance(payload["items"], list)


@pytest.mark.asyncio
async def test_list_options_filter_by_field(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can filter dropdown options by field name."""
    response = await client.get(
        "/api/v1/admin/dropdowns?field_name=specialty", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    # All returned items must belong to 'specialty'
    for item in data["items"]:
        assert item["field_name"] == "specialty"


@pytest.mark.asyncio
async def test_list_options_filter_by_status(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can filter dropdown options by status."""
    response = await client.get(
        "/api/v1/admin/dropdowns?status=approved", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    for item in data["items"]:
        assert item["status"] == "approved"


@pytest.mark.asyncio
async def test_list_options_requires_auth(client: AsyncClient) -> None:
    """List options endpoint requires authentication."""
    response = await client.get("/api/v1/admin/dropdowns")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /admin/dropdowns/pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pending_options(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can list all pending dropdown options."""
    response = await client.get("/api/v1/admin/dropdowns/pending", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    payload = data["data"]
    assert "items" in payload
    assert "pending_count" in payload
    # All returned items must be pending
    for item in payload["items"]:
        assert item["status"] == "pending"


# ---------------------------------------------------------------------------
# POST /admin/dropdowns  — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_option(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can create a new dropdown option (approved immediately)."""
    payload = {
        "field_name": "specialty",
        "value": "AdminCreatedSpecialty",
        "label": "Admin Created Specialty",
        "display_order": 99,
        "is_system": False,
    }
    response = await client.post("/api/v1/admin/dropdowns", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert "data" in data
    option = data["data"]
    assert option["field_name"] == "specialty"
    assert option["value"] == "AdminCreatedSpecialty"
    assert option["status"] == "approved"  # Admin creates are immediately approved
    assert option["label"] == "Admin Created Specialty"


@pytest.mark.asyncio
async def test_create_option_duplicate_returns_409(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Creating a duplicate option returns 409 Conflict."""
    payload = {
        "field_name": "specialty",
        "value": "DuplicateValue_XYZ123",
        "label": "Duplicate Value",
    }
    # First creation succeeds
    first = await client.post("/api/v1/admin/dropdowns", json=payload, headers=auth_headers)
    assert first.status_code == 201

    # Second creation with same field+value → 409
    second = await client.post("/api/v1/admin/dropdowns", json=payload, headers=auth_headers)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_create_option_requires_auth(client: AsyncClient) -> None:
    """Create option endpoint requires authentication."""
    payload = {"field_name": "specialty", "value": "Unauthenticated"}
    response = await client.post("/api/v1/admin/dropdowns", json=payload)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /admin/dropdowns/{option_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_option_by_id(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can fetch a single dropdown option by ID."""
    # First create one so we know its ID
    create_resp = await client.post(
        "/api/v1/admin/dropdowns",
        json={"field_name": "specialty", "value": "GetByIdSpecialty"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    option_id = create_resp.json()["data"]["id"]

    response = await client.get(f"/api/v1/admin/dropdowns/{option_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == option_id
    assert data["value"] == "GetByIdSpecialty"


@pytest.mark.asyncio
async def test_get_nonexistent_option_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Getting an option that does not exist returns 404."""
    response = await client.get("/api/v1/admin/dropdowns/999999", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /admin/dropdowns/{option_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_option_label(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can update a dropdown option's label and display_order."""
    # Create first
    create_resp = await client.post(
        "/api/v1/admin/dropdowns",
        json={"field_name": "specialty", "value": "UpdateLabelSpecialty"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    option_id = create_resp.json()["data"]["id"]

    # Update
    update_resp = await client.patch(
        f"/api/v1/admin/dropdowns/{option_id}",
        json={"label": "Updated Label", "display_order": 5},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["label"] == "Updated Label"
    assert updated["display_order"] == 5


@pytest.mark.asyncio
async def test_update_nonexistent_option_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Patching an option that does not exist returns 404."""
    response = await client.patch(
        "/api/v1/admin/dropdowns/999999",
        json={"label": "Ghost Label"},
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /admin/dropdowns/{option_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_option(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can delete a non-system dropdown option."""
    # Create a non-system option
    create_resp = await client.post(
        "/api/v1/admin/dropdowns",
        json={"field_name": "specialty", "value": "DeleteMeSpecialty", "is_system": False},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    option_id = create_resp.json()["data"]["id"]

    delete_resp = await client.delete(
        f"/api/v1/admin/dropdowns/{option_id}", headers=auth_headers
    )
    assert delete_resp.status_code == 200
    result = delete_resp.json()["data"]
    assert result["deleted"] is True
    assert result["option_id"] == option_id


@pytest.mark.asyncio
async def test_delete_system_option_returns_403(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Deleting a system-seeded option returns 403."""
    # Create a system option
    create_resp = await client.post(
        "/api/v1/admin/dropdowns",
        json={"field_name": "specialty", "value": "SystemProtected_XYZ", "is_system": True},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    option_id = create_resp.json()["data"]["id"]

    delete_resp = await client.delete(
        f"/api/v1/admin/dropdowns/{option_id}", headers=auth_headers
    )
    assert delete_resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_nonexistent_option_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Deleting an option that does not exist returns 404."""
    response = await client.delete("/api/v1/admin/dropdowns/999999", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/dropdowns/{option_id}/approve  — approve single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_pending_option(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can approve a PENDING dropdown option submitted by a user."""
    # Submit a pending option via the public endpoint first
    submit_resp = await client.post(
        "/api/v1/dropdowns/submit",
        json={"field_name": "specialty", "value": "UserPendingSpecialty"},
        headers=auth_headers,
    )
    assert submit_resp.status_code == 202
    option_id = submit_resp.json()["data"]["id"]

    # Approve it
    approve_resp = await client.post(
        f"/api/v1/admin/dropdowns/{option_id}/approve",
        json={"review_notes": "Looks good"},
        headers=auth_headers,
    )
    assert approve_resp.status_code == 200
    approved = approve_resp.json()["data"]
    assert approved["status"] == "approved"
    assert approved["review_notes"] == "Looks good"


@pytest.mark.asyncio
async def test_approve_nonexistent_option_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Approving a non-existent option returns 404."""
    response = await client.post(
        "/api/v1/admin/dropdowns/999999/approve",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/dropdowns/{option_id}/reject  — reject single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_pending_option(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can reject a PENDING dropdown option."""
    # Submit a pending option
    submit_resp = await client.post(
        "/api/v1/dropdowns/submit",
        json={"field_name": "specialty", "value": "UserPendingReject"},
        headers=auth_headers,
    )
    assert submit_resp.status_code == 202
    option_id = submit_resp.json()["data"]["id"]

    # Reject it
    reject_resp = await client.post(
        f"/api/v1/admin/dropdowns/{option_id}/reject",
        json={"review_notes": "Does not meet quality standards"},
        headers=auth_headers,
    )
    assert reject_resp.status_code == 200
    rejected = reject_resp.json()["data"]
    assert rejected["status"] == "rejected"
    assert rejected["review_notes"] == "Does not meet quality standards"


# ---------------------------------------------------------------------------
# POST /admin/dropdowns/bulk-approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_approve(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can bulk-approve multiple PENDING options."""
    # Submit two pending options
    ids = []
    for i in range(2):
        resp = await client.post(
            "/api/v1/dropdowns/submit",
            json={"field_name": "specialty", "value": f"BulkApproveSpecialty_{i}"},
            headers=auth_headers,
        )
        assert resp.status_code == 202
        ids.append(resp.json()["data"]["id"])

    bulk_resp = await client.post(
        "/api/v1/admin/dropdowns/bulk-approve",
        json={"option_ids": ids, "review_notes": "Batch approval"},
        headers=auth_headers,
    )
    assert bulk_resp.status_code == 200
    result = bulk_resp.json()["data"]
    assert result["action"] == "approved"
    assert result["updated_count"] == 2


# ---------------------------------------------------------------------------
# POST /admin/dropdowns/bulk-reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_reject(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Admin can bulk-reject multiple PENDING options."""
    # Submit two pending options
    ids = []
    for i in range(2):
        resp = await client.post(
            "/api/v1/dropdowns/submit",
            json={"field_name": "specialty", "value": f"BulkRejectSpecialty_{i}"},
            headers=auth_headers,
        )
        assert resp.status_code == 202
        ids.append(resp.json()["data"]["id"])

    bulk_resp = await client.post(
        "/api/v1/admin/dropdowns/bulk-reject",
        json={"option_ids": ids, "review_notes": "Not acceptable"},
        headers=auth_headers,
    )
    assert bulk_resp.status_code == 200
    result = bulk_resp.json()["data"]
    assert result["action"] == "rejected"
    assert result["updated_count"] == 2
