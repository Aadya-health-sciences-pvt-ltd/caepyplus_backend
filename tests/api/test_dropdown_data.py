"""Tests for public dropdown endpoints — /api/v1/dropdowns/*."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


# ---------------------------------------------------------------------------
# GET /dropdowns  — all approved options (public, no auth required)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_dropdowns_public(client: AsyncClient) -> None:
    """Public endpoint returns all approved dropdown fields without auth."""
    response = await client.get("/api/v1/dropdowns")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "data" in data
    payload = data["data"]
    assert "fields" in payload
    assert "supported_fields" in payload
    assert isinstance(payload["supported_fields"], list)
    assert len(payload["supported_fields"]) > 0


@pytest.mark.asyncio
async def test_all_dropdowns_contains_specialty_field(client: AsyncClient) -> None:
    """The all-dropdowns response contains the 'specialty' field."""
    response = await client.get("/api/v1/dropdowns")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert "specialty" in payload["fields"]
    specialty = payload["fields"]["specialty"]
    assert "field_name" in specialty
    assert "description" in specialty
    assert "options" in specialty
    assert isinstance(specialty["options"], list)


@pytest.mark.asyncio
async def test_all_dropdowns_options_have_correct_shape(client: AsyncClient) -> None:
    """Each option in the public response has id, value, label, display_order."""
    response = await client.get("/api/v1/dropdowns")
    assert response.status_code == 200
    payload = response.json()["data"]
    for _field_name, field_data in payload["fields"].items():
        for option in field_data["options"]:
            assert "id" in option
            assert "value" in option
            assert "label" in option
            assert "display_order" in option


# ---------------------------------------------------------------------------
# GET /dropdowns/{field_name}  — single field (public)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_single_field_specialty(client: AsyncClient) -> None:
    """Public endpoint returns options for a single field."""
    response = await client.get("/api/v1/dropdowns/specialty")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    field_data = data["data"]
    assert field_data["field_name"] == "specialty"
    assert "description" in field_data
    assert "options" in field_data
    assert isinstance(field_data["options"], list)


@pytest.mark.asyncio
async def test_get_single_field_qualifications(client: AsyncClient) -> None:
    """Public endpoint returns options for the qualifications field."""
    response = await client.get("/api/v1/dropdowns/qualifications")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["field_name"] == "qualifications"


@pytest.mark.asyncio
async def test_get_unknown_field_returns_404(client: AsyncClient) -> None:
    """Requesting an unsupported field name returns 404."""
    response = await client.get("/api/v1/dropdowns/nonexistent_field")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_single_field_no_auth_required(client: AsyncClient) -> None:
    """Single-field endpoint is public — no auth needed."""
    response = await client.get("/api/v1/dropdowns/specialty")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /dropdowns/submit  — user submits new option (authenticated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_new_option(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Authenticated user can propose a new dropdown value (→ PENDING)."""
    payload = {
        "field_name": "specialty",
        "value": "UserSubmittedSpecialty_test",
        "label": "User Submitted Specialty",
    }
    response = await client.post("/api/v1/dropdowns/submit", json=payload, headers=auth_headers)
    assert response.status_code == 202
    data = response.json()
    assert "data" in data
    result = data["data"]
    assert result["field_name"] == "specialty"
    assert result["value"] == "UserSubmittedSpecialty_test"
    assert result["status"] == "pending"  # User submissions start as pending


@pytest.mark.asyncio
async def test_submit_option_requires_auth(client: AsyncClient) -> None:
    """Submitting a new option requires authentication."""
    payload = {"field_name": "specialty", "value": "UnauthSubmit"}
    response = await client.post("/api/v1/dropdowns/submit", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_submit_unsupported_field_returns_422(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Submitting to an unsupported field returns 422."""
    payload = {"field_name": "invalid_field_xyz", "value": "Some Value"}
    response = await client.post("/api/v1/dropdowns/submit", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_duplicate_returns_existing_record(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Re-submitting the same value returns the existing record (not a duplicate)."""
    payload = {"field_name": "specialty", "value": "DedupeSpecialty_ABC"}

    # First submission
    first = await client.post("/api/v1/dropdowns/submit", json=payload, headers=auth_headers)
    assert first.status_code == 202

    # Second submission with same value — should return existing record, not error
    second = await client.post("/api/v1/dropdowns/submit", json=payload, headers=auth_headers)
    # Returns 202 with the existing record (idempotent — no duplicate created)
    assert second.status_code == 202
    first_id = first.json()["data"]["id"]
    second_id = second.json()["data"]["id"]
    assert first_id == second_id  # Same record returned


@pytest.mark.asyncio
async def test_submit_option_visible_after_admin_approval(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """A submitted option becomes visible in public endpoints only after approval."""
    unique_value = "VisibilityTestSpecialty_XYZ789"

    # 1. Submit as user → PENDING
    submit_resp = await client.post(
        "/api/v1/dropdowns/submit",
        json={"field_name": "specialty", "value": unique_value},
        headers=auth_headers,
    )
    assert submit_resp.status_code == 202
    option_id = submit_resp.json()["data"]["id"]

    # 2. Confirm not yet visible in public endpoint (still pending)
    public_resp = await client.get("/api/v1/dropdowns/specialty")
    assert public_resp.status_code == 200
    public_values = [opt["value"] for opt in public_resp.json()["data"]["options"]]
    assert unique_value not in public_values

    # 3. Admin approves it
    approve_resp = await client.post(
        f"/api/v1/admin/dropdowns/{option_id}/approve",
        json={},
        headers=auth_headers,
    )
    assert approve_resp.status_code == 200

    # 4. Now visible in public endpoint
    public_resp_after = await client.get("/api/v1/dropdowns/specialty")
    assert public_resp_after.status_code == 200
    public_values_after = [opt["value"] for opt in public_resp_after.json()["data"]["options"]]
    assert unique_value in public_values_after


@pytest.mark.asyncio
async def test_submit_option_not_visible_after_rejection(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """A rejected option never appears in the public dropdown."""
    unique_value = "RejectedSpecialty_ABC456"

    # Submit
    submit_resp = await client.post(
        "/api/v1/dropdowns/submit",
        json={"field_name": "specialty", "value": unique_value},
        headers=auth_headers,
    )
    assert submit_resp.status_code == 202
    option_id = submit_resp.json()["data"]["id"]

    # Admin rejects
    reject_resp = await client.post(
        f"/api/v1/admin/dropdowns/{option_id}/reject",
        json={"review_notes": "Not accepted"},
        headers=auth_headers,
    )
    assert reject_resp.status_code == 200

    # Still not visible in public endpoint
    public_resp = await client.get("/api/v1/dropdowns/specialty")
    assert public_resp.status_code == 200
    public_values = [opt["value"] for opt in public_resp.json()["data"]["options"]]
    assert unique_value not in public_values
