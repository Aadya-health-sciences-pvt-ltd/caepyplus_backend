"""
Doctor Onboarding Service — Application Entry Point.

This module wires together:
- FastAPI application factory with production-grade middleware
- Structured logging (structlog)
- CORS, security-headers middleware
- Global exception handlers
- Lifespan: DB health check on startup, graceful shutdown
"""
from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .api.v1 import router as v1_router
from .core.config import get_settings
from .core.exceptions import AppException
from .core.prompts import get_prompt_manager
from .core.responses import ErrorDetail, ErrorResponse, ResponseMeta
from .db.session import close_db, get_db_manager
from .services import otp_service as _otp_service_module
from .services.voice_service import get_voice_service

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def configure_logging() -> None:
    """Configure structured logging via structlog."""
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            (
                structlog.dev.ConsoleRenderer()
                if settings.is_development
                else structlog.processors.JSONRenderer()
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route standard-library logging through the same level so third-party
    # libraries (SQLAlchemy, uvicorn, httpx …) respect the configured level.
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=log_level,
        stream=sys.stdout,
    )


# ---------------------------------------------------------------------------
# Security-headers middleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security-hardening HTTP response headers on every response.

    These headers are a defence-in-depth layer and do not replace proper
    authentication / authorisation controls.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # Strict-Transport-Security is only meaningful over HTTPS.
        # The reverse proxy / load-balancer in production should enforce HTTPS;
        # we set it here as a belt-and-suspenders measure.
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
        # Content-Security-Policy — relax for Swagger / ReDoc docs paths in
        # development so the browser can load their inline scripts and styles.
        # All other paths (and all of production) use the strict locked-down policy.
        _settings = get_settings()
        root_prefix = (
            "/" + _settings.ROOT_PATH.strip("/")
        ) if _settings.ROOT_PATH else ""
        docs_paths = {
            f"{root_prefix}/docs",
            f"{root_prefix}/redoc",
            f"{root_prefix}/openapi.json",
        }
        if request.url.path in docs_paths and _settings.APP_ENV != "production":
            # Swagger UI loads JS/CSS from jsdelivr CDN and favicon from fastapi.tiangolo.com
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "frame-ancestors 'none'; "
                "base-uri 'none'"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
            )
        return response


# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request/response pair.

    The middleware honours an incoming ``X-Request-ID`` header so that
    external systems (API gateways, load balancers) can inject their own
    correlation IDs and have them propagated all the way through.

    The ID is:
    - Stored in ``request.state.request_id`` for access inside endpoints.
    - Returned in the ``X-Request-ID`` response header for the client.
    - Bound to the structlog context so every log line for this request
      automatically includes ``request_id=...``.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        # Bind to structlog context so all log lines for this request carry it.
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown.

    Startup:
        1. Configure logging.
        2. Verify database connectivity (health check only — schema
           management is handled exclusively by Alembic migrations, NOT
           by SQLAlchemy's ``create_all``).
        3. Start background voice-session cleanup task.

    Shutdown:
        1. Cancel background tasks gracefully.
        2. Close all database connections.caepz
    """
    import asyncio

    settings = get_settings()
    logger = structlog.get_logger()
    cleanup_task: asyncio.Task[None] | None = None

    async def _periodic_session_cleanup() -> None:
        """Purge expired voice sessions every 5 minutes."""
        while True:
            try:
                await asyncio.sleep(300)
                cleaned = await get_voice_service().store.cleanup_expired()
                if cleaned > 0:
                    logger.info("Cleaned up expired voice sessions", count=cleaned)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Session cleanup error", error=str(exc))

    # ---- Startup ----
    configure_logging()

    logger.info(
        "Starting application",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )

    # Warm up the prompt manager eagerly at startup so the synchronous YAML
    # file read (open() in _load_prompts) never blocks the event loop during
    # live request handling.
    try:
        get_prompt_manager()
        logger.info("Prompt manager initialized")
    except Exception as exc:
        logger.warning("Prompt manager initialization failed", error=str(exc))

    db_manager = get_db_manager()

    # Verify DB connectivity — schema is managed solely by Alembic.
    # We intentionally do NOT call create_tables() here; run
    #   scripts/migrate.py  (or  alembic upgrade head)
    # before the first deployment and after every schema change.
    db_health = await db_manager.health_check()
    logger.info("Database health check", result=db_health)

    cleanup_task = asyncio.create_task(_periodic_session_cleanup())

    logger.info("Application started successfully")

    yield

    # ---- Shutdown ----
    logger.info("Shutting down application")

    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

    await close_db()

    # Close OTP service resources (httpx client + Redis connection) if the
    # service was ever initialized during this process's lifetime.
    if _otp_service_module._otp_service is not None:
        try:
            await _otp_service_module._otp_service.close()
            logger.info("OTP service closed")
        except Exception as exc:
            logger.warning("OTP service close error", error=str(exc))

    logger.info("Application shutdown complete")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    tags_metadata = [
        {
            "name": "Health",
            "description": "🏥 Health checks — liveness, readiness, and comprehensive status.",
        },
        {
            "name": "Authentication",
            "description": "🔐 OTP-based and Google OAuth login; returns JWT access tokens.",
        },
        {
            "name": "Doctors",
            "description": (
                "👨‍⚕️ Doctor profile management — CRUD, paginated listing, "
                "admin lookup, and CSV bulk upload."
            ),
        },
        {
            "name": "Onboarding",
            "description": (
                "📄 AI-powered resume extraction, profile submission, "
                "admin verification / rejection."
            ),
        },
        {
            "name": "Voice Onboarding",
            "description": "🎤 Natural language voice session — start, chat.",
        },
        {
            "name": "Onboarding Admin",
            "description": "🛠️ Internal admin CRUD for identity, details, media, and status history.",
        },
        {
            "name": "Admin - User Management",
            "description": "👥 Manage admin and operation user accounts (RBAC).",
        },
        {
            "name": "Dropdowns",
            "description": (
                "📋 Public dropdown options (approved values only). "
                "Authenticated users can propose new values via POST /dropdowns/submit."
            ),
        },
        {
            "name": "Admin - Dropdowns",
            "description": (
                "🗂️ Admin CRUD and approval workflow for dropdown options. "
                "Approve or reject user-submitted values, manage seed data."
            ),
        },
    ]

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="""
# 🏥 Doctor Onboarding Smart-Fill API

Production-grade REST API for doctor onboarding with AI-powered data extraction.

## Key Features

| Feature | Description |
|---------|-------------|
| 📄 **Resume Extraction** | Upload PDF/Image resumes; extract structured data via Gemini Vision |
| 👨‍⚕️ **Doctor Management** | Full CRUD with paginated listing and CSV bulk upload |
| 🎤 **Voice Onboarding** | Natural language conversation for hands-free data collection |
| 🔐 **Auth** | OTP (mobile) + Google OAuth; JWT with role-based access control |

## API Versioning

All endpoints are versioned under `/api/v1/`.
        """,
        # Docs are only available in non-production environments.
        # When ROOT_PATH is set, serve docs/openapi.json under that base path.
        docs_url=(
            f"{settings.ROOT_PATH.rstrip('/')}/docs" if settings.ROOT_PATH else "/docs"
        )
        if settings.is_development
        else None,
        redoc_url=(
            f"{settings.ROOT_PATH.rstrip('/')}/redoc" if settings.ROOT_PATH else "/redoc"
        )
        if settings.is_development
        else None,
        openapi_url=(
            f"{settings.ROOT_PATH.rstrip('/')}/openapi.json"
            if settings.ROOT_PATH
            else "/openapi.json"
        )
        if settings.is_development
        else None,
        default_response_class=JSONResponse,
        lifespan=lifespan,
        openapi_tags=tags_metadata,
        swagger_ui_parameters={
            "docExpansion": "list",
            "defaultModelsExpandDepth": 2,
            "filter": True,
            "tryItOutEnabled": True,
        },
        license_info={"name": "MIT License", "url": "https://opensource.org/licenses/MIT"},
        contact={"name": "API Support", "email": "support@linqmd.com"},
    )

    # Normalize ROOT_PATH for mounting: ensure leading slash (e.g. caepyplus/api -> /caepyplus/api).
    # When set, all API routes are served under this path when running the app
    # directly (no reverse-proxy path stripping).
    root_prefix = ("/" + settings.ROOT_PATH.strip("/")) if settings.ROOT_PATH else ""

    # ------------------------------------------------------------------
    # Middleware — order matters: first registered = outermost wrapper
    # ------------------------------------------------------------------

    # 1. Security headers (outermost — applies to all responses)
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. Request-ID — assigns a unique ID per request, returns it in
    #    X-Request-ID header, and binds it to structlog context so every
    #    log line emitted during the request carries request_id=<uuid>.
    app.add_middleware(RequestIDMiddleware)

    # 3. CORS — must be after security headers so preflight OPTIONS
    #    responses also receive security headers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.cors_methods_list,
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------
    _register_exception_handlers(app)

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    # Mount API v1 under root_prefix so endpoints live at e.g. /caepyplus/api/v1/health
    app.include_router(v1_router, prefix=root_prefix)

    # Root — not in OpenAPI schema; links must include root_prefix when set
    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        health_path = f"{root_prefix}/v1/health" if root_prefix else "/v1/health"
        payload: dict[str, str] = {
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "health": health_path,
        }
        if settings.is_development:
            payload["docs"] = f"{root_prefix}/docs" if root_prefix else "/docs"
        return payload

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the application."""
    logger = structlog.get_logger()

    @app.exception_handler(AppException)
    async def _app_exc(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "Application exception",
            error_code=exc.error_code,
            message=exc.message,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorDetail(code=exc.error_code, message=exc.message, details=exc.details),
                meta=ResponseMeta(),
            ).model_dump(mode='json'),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("Validation error", errors=exc.errors(), path=str(request.url))
        validation_errors = [
            {
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message="Request validation failed",
                    details={"validation_errors": validation_errors},
                ),
                meta=ResponseMeta(),
            ).model_dump(mode='json'),
        )

    @app.exception_handler(Exception)
    async def _generic_exc(request: Request, exc: Exception) -> JSONResponse:
        settings = get_settings()
        logger.exception("Unhandled exception", error=str(exc), path=str(request.url))
        # Never expose internal details in production
        message = str(exc) if settings.DEBUG else "An unexpected error occurred"
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(code="INTERNAL_ERROR", message=message),
                meta=ResponseMeta(),
            ).model_dump(mode='json'),
        )


# ---------------------------------------------------------------------------
# Module-level application instance (consumed by uvicorn / gunicorn)
# ---------------------------------------------------------------------------
app = create_application()
