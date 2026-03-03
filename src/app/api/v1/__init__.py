"""API v1 — versioned router.

Router structure
----------------
PUBLIC (no auth):
  /health            → health checks (liveness, readiness)
  /auth/*            → OTP request/verify/resend + Google OAuth
  /dropdowns         → GET all approved dropdown options
  /dropdowns/{field} → GET approved options for one field

AUTHENTICATED (require valid JWT):
  /onboarding/*      → resume extraction, submit, verify, reject
  /voice/*           → AI voice session (start, chat)
  /doctors/*         → CRUD + lookup + CSV bulk upload
  /dropdowns/submit  → propose a new dropdown value (→ PENDING)

ADMIN (require authentication; RBAC enforced at endpoint level):
  /onboarding-admin/*  → identity, details, media, status, doctor list/lookup
  /admin/users/*       → user management (list, create, update)
  /admin/dropdowns/*   → dropdown CRUD + approve / reject workflow
"""
from fastapi import APIRouter, Depends

from ...core.security import require_authentication
from .endpoints import (
    admin_dropdowns,
    admin_users,
    doctors,
    dropdowns,
    health,
    onboarding,
    onboarding_admin,
    otp,
    voice,
)

router = APIRouter(prefix="/v1")

# =========================================================================
# PUBLIC ENDPOINTS — no auth required
# =========================================================================

# Health probes: liveness, readiness, comprehensive status
router.include_router(health.router, tags=["Health"])

# Authentication: OTP request/verify/resend, admin OTP, Google OAuth
router.include_router(otp.router, tags=["Authentication"])

# Dropdown public read: approved options visible to everyone (no login needed).
# NOTE: /dropdowns/submit (POST) is protected — the router itself handles
# the auth check per-endpoint so no router-level dependency here.
router.include_router(dropdowns.router, tags=["Dropdowns"])

# =========================================================================
# AUTHENTICATED ENDPOINTS — require valid JWT
# =========================================================================

router.include_router(
    onboarding.router,
    tags=["Onboarding"],
    dependencies=[Depends(require_authentication)],
)

router.include_router(
    voice.router,
    tags=["Voice Onboarding"],
    dependencies=[Depends(require_authentication)],
)

router.include_router(
    doctors.router,
    tags=["Doctors"],
    dependencies=[Depends(require_authentication)],
)

# =========================================================================
# ADMIN ENDPOINTS — require auth; role enforcement is per-endpoint
# =========================================================================

# Onboarding admin: full doctor onboarding CRUD + lookup
router.include_router(
    onboarding_admin.router,
    dependencies=[Depends(require_authentication)],
)

# Admin user management: list / create / update admin & operational users.
#
# !! NO router-level auth dependency here — intentional !!
# The /admin/users/seed endpoint is a public bootstrap route (self-disabling
# once an admin exists) and cannot carry a router-level auth dependency.
# Every other endpoint in admin_users.router MUST individually declare an
# AdminUser or AdminOrOperationalUser dependency — code-review this invariant
# on every future change to that module.
router.include_router(
    admin_users.router,
    tags=["Admin - User Management"],
)

# Admin dropdown management: CRUD + approve / reject user submissions.
# All endpoints in admin_dropdowns declare AdminOrOperationalUser dependency.
router.include_router(
    admin_dropdowns.router,
    dependencies=[Depends(require_authentication)],
    tags=["Admin - Dropdowns"],
)
