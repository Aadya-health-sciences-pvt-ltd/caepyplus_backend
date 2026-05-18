"""Unit tests for health check endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """Test the health check endpoint returns valid status."""
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    # Status can be "healthy" or "degraded" (if GOOGLE_API_KEY not set)
    assert data["status"] in ("healthy", "degraded")
    assert data["service"] == "doctor-onboarding-service"
    assert data["version"] == "2.0.0"
    assert "checks" in data
    # Database should always be healthy in tests
    assert data["checks"]["database"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_check(client: AsyncClient) -> None:
    """Test the readiness check endpoint."""
    response = await client.get("/api/v1/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"


@pytest.mark.asyncio
async def test_liveness_check(client: AsyncClient) -> None:
    """Test the liveness check endpoint."""
    response = await client.get("/api/v1/live")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
