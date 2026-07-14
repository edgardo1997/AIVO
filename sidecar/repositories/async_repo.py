"""Async repository base class for SQLAlchemy async sessions."""

import logging
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Base

log = logging.getLogger("sentinel.db.async_repo")

ModelT = TypeVar("ModelT", bound=Base)


class AsyncRepository(Generic[ModelT]):
    """Async repository with common CRUD operations."""

    def __init__(self, model_class: Type[ModelT], session: AsyncSession):
        self._model = model_class
        self._session = session

    async def get(self, ident: Any) -> Optional[ModelT]:
        return await self._session.get(self._model, ident)

    async def list_all(self) -> List[ModelT]:
        result = await self._session.execute(select(self._model))
        return list(result.scalars().all())

    async def add(self, instance: ModelT) -> ModelT:
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def update(self, instance: ModelT) -> ModelT:
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def delete(self, ident: Any) -> bool:
        instance = await self.get(ident)
        if instance is None:
            return False
        await self._session.delete(instance)
        await self._session.flush()
        return True

    async def delete_by(self, **filters: Any) -> int:
        stmt = sa_delete(self._model).filter_by(**filters)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def find_one(self, **filters: Any) -> Optional[ModelT]:
        stmt = select(self._model).filter_by(**filters).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_all(self, **filters: Any) -> List[ModelT]:
        stmt = select(self._model).filter_by(**filters)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters: Any) -> int:
        from sqlalchemy import func
        stmt = select(func.count()).select_from(self._model).filter_by(**filters)
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def execute_raw(self, stmt: Any) -> Any:
        return await self._session.execute(stmt)
