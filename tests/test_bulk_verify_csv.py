"""Tests for BULK_VERIFY flag on bulk CSV confirm."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.app.main import app


def _core_csv_body(phone: str = "9876500088") -> bytes:
    return (
        "phone,email,full_name,specialty,city,languages,medical_registration_number,"
        "medical_council,year_of_mbbs,theme\n"
        f"{phone},bulk.verify@example.com,Dr. Bulk Verify,Cardiology,Bangalore,"
        "English,REG-BV-1,Karnataka Medical Council,2012,dp_3\n"
    ).encode("utf-8")


@pytest.mark.asyncio
async def test_bulk_csv_validate_rejects_invalid_theme(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    csv_body = (
        "phone,email,full_name,specialty,medical_registration_number,medical_council,theme\n"
        "9876500077,bad@example.com,Dr. Bad Theme,Cardiology,REG1,Council,not_a_theme\n"
    )
    response = await client.post(
        "/api/v1/doctors/bulk-upload/csv/validate",
        headers=auth_headers,
        files={"file": ("bad-theme.csv", csv_body.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any(e["field"] == "theme" for e in data["errors"])


@pytest.mark.asyncio
async def test_bulk_confirm_with_bulk_verify_calls_post_upload(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    from src.app.core.config import get_settings
    from src.app.services.bulk_csv_post_upload import BulkPostUploadOutcome

    settings = get_settings().model_copy(update={"BULK_VERIFY": True})
    app.dependency_overrides[get_settings] = lambda: settings

    try:
        with patch(
            "src.app.api.v1.endpoints.doctors.apply_bulk_verify_and_linqmd",
            new_callable=AsyncMock,
        ) as mock_apply:
            mock_apply.return_value = BulkPostUploadOutcome(onboarding_status="verified")
            response = await client.post(
                "/api/v1/doctors/bulk-upload/csv",
                headers=auth_headers,
                files={"file": ("bulk.csv", _core_csv_body(), "text/csv")},
            )

        assert response.status_code == 200, response.text
        mock_apply.assert_called()
        data = response.json()
        assert data["created"] == 1
        assert data["rows"][0].get("onboarding_status") == "verified"
    finally:
        app.dependency_overrides.pop(get_settings, None)
