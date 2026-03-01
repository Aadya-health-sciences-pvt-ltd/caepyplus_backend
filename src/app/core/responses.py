"""
Standardized API Response Schemas.

Provides consistent response structures across all API endpoints.
Uses generic types for type-safe responses.
"""
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

# Generic type for response data
T = TypeVar("T")


class ResponseMeta(BaseModel):
    """Metadata included in all API responses."""

    request_id: str | None = Field(
        default=None,
        description="Unique request identifier for tracing"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Response timestamp (UTC)"
    )
    version: str = Field(
        default="2.0.0",
        description="API version"
    )


class GenericResponse(BaseModel, Generic[T]):
    """
    Generic wrapper for successful API responses.
    
    Provides a consistent structure for all successful responses:
    - success: Always True for successful responses
    - message: Human-readable success message
    - data: The actual response payload (typed via generic)
    - meta: Request metadata for tracing and debugging
    
    Example:
        ```python
        @router.get("/doctors/{doctor_id}", response_model=GenericResponse[DoctorResponse])
        async def get_doctor(doctor_id: int) -> GenericResponse[DoctorResponse]:
            doctor = await doctor_service.get_by_id(doctor_id)
            return GenericResponse(
                message="Doctor retrieved successfully",
                data=doctor,
            )
        ```
    """

    success: bool = Field(
        default=True,
        description="Indicates successful response"
    )
    message: str = Field(
        description="Human-readable response message"
    )
    data: T = Field(
        description="Response payload"
    )
    meta: ResponseMeta = Field(
        default_factory=ResponseMeta,
        description="Response metadata"
    )


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic wrapper for paginated list responses.
    
    Includes pagination metadata alongside the data list.
    """

    success: bool = Field(default=True)
    message: str
    data: list[T] = Field(description="List of items")
    pagination: "PaginationMeta"
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""

    total: int = Field(description="Total number of items")
    page: int = Field(ge=1, description="Current page number")
    page_size: int = Field(ge=1, le=100, description="Items per page")
    total_pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Whether there are more pages")
    has_previous: bool = Field(description="Whether there are previous pages")

    @classmethod
    def from_total(cls, total: int, page: int, page_size: int) -> "PaginationMeta":
        """Create pagination meta from total count."""
        total_pages = max(1, (total + page_size - 1) // page_size)
        return cls(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )


class ErrorDetail(BaseModel):
    """Detailed error information."""

    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error message")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Additional error context"
    )


class ErrorResponse(BaseModel):
    """
    Standardized error response structure.
    
    Used by the global exception handler for all error responses.
    """

    success: bool = Field(default=False)
    error: ErrorDetail
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(description="Service health status")
    service: str = Field(description="Service name")
    version: str = Field(description="Service version")
    environment: str = Field(description="Deployment environment")
    checks: dict[str, "HealthCheck"] = Field(
        default_factory=dict,
        description="Individual component health checks"
    )


class HealthCheck(BaseModel):
    """Individual health check result."""

    status: str = Field(description="Component status: healthy/unhealthy/degraded")
    latency_ms: float | None = Field(
        default=None,
        description="Response time in milliseconds"
    )
    message: str | None = Field(
        default=None,
        description="Additional status information"
    )


# Update forward references
PaginatedResponse.model_rebuild()
HealthResponse.model_rebuild()
