"""Linq360 dashboard feature (repository → service → controller → response)."""


def __getattr__(name: str):
    if name == "content_engagement_router":
        from .config.routing import router as content_engagement_router

        return content_engagement_router
    if name == "glance_router":
        from .config.routing import public_router as glance_router

        return glance_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["content_engagement_router", "glance_router"]
