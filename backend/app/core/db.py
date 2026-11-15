"""Async SQLAlchemy engine / session factory (PostgreSQL via asyncpg)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


class Database:
    """Owns the engine. One instance per process (``app.state.db``)."""

    def __init__(self, url: str, *, pool_size: int = 10, null_pool: bool = False) -> None:
        if null_pool:
            self.engine: AsyncEngine = create_async_engine(url, poolclass=NullPool)
        else:
            self.engine = create_async_engine(url, pool_size=pool_size, pool_pre_ping=True)
        self.sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as s:
            yield s

    async def dispose(self) -> None:
        await self.engine.dispose()
