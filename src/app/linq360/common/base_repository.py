"""Base repository for LinQ360 data access."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Session-bound repository with shared flush/add helpers."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, row: ModelT) -> ModelT:
        self.session.add(row)
        await self.session.flush()
        return row

    async def flush(self) -> None:
        await self.session.flush()

    async def get_by_pk(self, pk: Any) -> ModelT | None:
        return await self.session.get(self.model, pk)
