"""Base service for LinQ360 business logic."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseService:
    """Session-aware service base."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
