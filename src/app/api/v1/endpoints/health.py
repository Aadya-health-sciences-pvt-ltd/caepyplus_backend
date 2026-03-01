"""
Health Check Endpoints.

Provides health and readiness endpoints for orchestration systems.
"""
import time
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.config import Settings, get_settings
from ....core.responses import HealthCheck, HealthResponse
from ....db.session import get_db

log = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the health status of the service and its dependencies.",
)
async def health_check(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HealthResponse:
    """
    Comprehensive health check endpoint.
    
    Checks:
    - Service status
    - Database connectivity
    - AI service availability (basic check)
    """
    checks: dict[str, HealthCheck] = {}

    # Database health check
    db_start = time.time()
    try:
        await db.execute(text("SELECT 1"))
        db_latency = (time.time() - db_start) * 1000
        checks["database"] = HealthCheck(
            status="healthy",
            latency_ms=round(db_latency, 2),
            message="Connected",
        )
    except Exception as e:
        log.error("db_health_check_failed", error=str(e))
        checks["database"] = HealthCheck(
            status="unhealthy",
            message="Database connection failed",
        )

    # AI service check (just config validation)
    if settings.GOOGLE_API_KEY:
        checks["ai_service"] = HealthCheck(
            status="healthy",
            message="API key configured",
        )
    else:
        checks["ai_service"] = HealthCheck(
            status="degraded",
            message="API key not configured",
        )

    # Overall status
    overall_status = "healthy"
    if any(c.status == "unhealthy" for c in checks.values()):
        overall_status = "unhealthy"
    elif any(c.status == "degraded" for c in checks.values()):
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        checks=checks,
    )


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Returns 200 if the service is ready to accept traffic.",
)
async def readiness_probe(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """
    Kubernetes readiness probe.
    
    Returns 200 only if all critical dependencies are available.
    """
    # Check database
    await db.execute(text("SELECT 1"))

    return {"status": "ready"}


@router.get(
    "/live",
    summary="Liveness probe",
    description="Returns 200 if the service is alive.",
)
async def liveness_probe() -> dict[str, str]:
    """
    Kubernetes liveness probe.
    
    Simple check that the service process is running.
    """
    return {"status": "alive"}
