"""Dashboard feature responses on top of common ResponseBuilder."""
from __future__ import annotations

from typing import Any

from ..common.response_builder import ResponseBuilder
from .dashboard_fields import GlanceApiResponse, GlanceResponse


class DashboardResponse:
    """Build glance / engagement envelopes for dashboard controllers."""

    def __init__(self) -> None:
        self._builder = ResponseBuilder()

    def glance_success(self, msg: str, data: dict[str, Any]) -> GlanceApiResponse:
        envelope = self._builder.success(msg, GlanceResponse.model_validate(data))
        return GlanceApiResponse.model_validate(envelope)

    def code_error(self, msg: str) -> GlanceApiResponse:
        envelope = self._builder.code_error(msg)
        return GlanceApiResponse.model_validate(envelope)
