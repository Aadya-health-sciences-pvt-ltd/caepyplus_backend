"""Dashboard route registration (paths → controller handlers)."""
from __future__ import annotations

from fastapi import APIRouter

from ..dashboard_controller import (
    dashboard_webhook,
    dashboard_websocket,
    get_content_engagement,
    get_glance_appointments,
    get_glance_content,
    sync_glance,
)
from ..dashboard_fields import (
    AppointmentsGlanceApiResponse,
    ContentEngagementResponse,
    ContentGlanceApiResponse,
)

router = APIRouter()
public_router = APIRouter()

router.add_api_route(
    "/doctors/{doctor_id}/content-engagement",
    get_content_engagement,
    methods=["GET"],
    response_model=ContentEngagementResponse,
)

public_router.add_api_route(
    "/glance/content",
    get_glance_content,
    methods=["GET"],
    response_model=ContentGlanceApiResponse,
)
public_router.add_api_route(
    "/glance/appointments",
    get_glance_appointments,
    methods=["GET"],
    response_model=AppointmentsGlanceApiResponse,
)
public_router.add_api_route(
    "/glance/sync",
    sync_glance,
    methods=["POST"],
    response_model=ContentGlanceApiResponse,
)
public_router.add_api_route(
    "/webhooks/dashboard",
    dashboard_webhook,
    methods=["POST"],
    response_model=AppointmentsGlanceApiResponse,
)
public_router.add_api_websocket_route(
    "/ws/dashboard",
    dashboard_websocket,
)
