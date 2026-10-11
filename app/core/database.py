from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _engine_options() -> dict[str, Any]:
    options: dict[str, Any] = {"pool_pre_ping": True}
    if settings.environment == "test":
        options["poolclass"] = NullPool
    return options


engine = create_async_engine(settings.database_url, **_engine_options())
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
