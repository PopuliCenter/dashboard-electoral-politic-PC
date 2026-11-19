"""Mesin database async dan sesi. Satu engine per proses."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        echo=settings.app_env == "development" and settings.log_level.lower() == "debug",
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


async def ping_database(session: AsyncSession) -> dict[str, str]:
    """Kembalikan versi PostgreSQL dan PostGIS. Melempar bila koneksi gagal."""
    postgres_version = (await session.execute(text("SHOW server_version"))).scalar_one()
    postgis_row = (
        await session.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'"))
    ).scalar_one_or_none()
    return {
        "postgres_version": str(postgres_version),
        "postgis_version": str(postgis_row) if postgis_row else "tidak terpasang",
    }
