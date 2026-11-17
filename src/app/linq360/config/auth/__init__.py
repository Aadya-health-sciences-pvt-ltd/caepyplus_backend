"""Linq360 auth dependencies."""
from .workspace_auth import (
    WorkspaceIdentityAuth,
    WorkspaceSelectAuth,
    require_dashboard_webhook_auth,
    require_identity_auth,
    require_workspace_select_auth,
)

__all__ = [
    "WorkspaceIdentityAuth",
    "WorkspaceSelectAuth",
    "require_dashboard_webhook_auth",
    "require_identity_auth",
    "require_workspace_select_auth",
]
