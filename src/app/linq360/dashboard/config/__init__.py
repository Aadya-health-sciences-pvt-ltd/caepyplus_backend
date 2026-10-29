"""Dashboard-owned config (routing + service)."""


def __getattr__(name: str):
    if name in {"DashboardService", "GlanceDashboardMissing"}:
        from .dashboard_service import DashboardService, GlanceDashboardMissing

        return {
            "DashboardService": DashboardService,
            "GlanceDashboardMissing": GlanceDashboardMissing,
        }[name]
    if name in {"router", "public_router"}:
        from . import routing

        return getattr(routing, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DashboardService",
    "GlanceDashboardMissing",
    "public_router",
    "router",
]
