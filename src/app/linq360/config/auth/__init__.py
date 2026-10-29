"""Linq360 auth dependencies."""
from .workspace_auth import (
    WorkspaceSelectAuth,
    require_dashboard_webhook_auth,
    require_workspace_select_auth,
)

__all__ = [
    "WorkspaceSelectAuth",
    "require_dashboard_webhook_auth",
    "require_workspace_select_auth",
]
