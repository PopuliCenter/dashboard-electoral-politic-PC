"""Fixture bersama.

Test unit tidak boleh butuh database. Test yang butuh database memakai fixture
`session`, ditandai `integration`, dan otomatis dilewati bila database mati.
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Sesi yang selalu di-rollback, jadi database uji tidak pernah berubah.

    Engine dibuat baru per test dengan NullPool: pytest-asyncio memakai event
    loop berbeda tiap test, dan koneksi asyncpg dari loop sebelumnya tidak bisa
    dipakai ulang.
    """
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        connection = await engine.connect()
    except (OSError, SQLAlchemyError) as exc:
        await engine.dispose()
        pytest.skip(f"database tidak tersedia: {type(exc).__name__}")

    transaction = await connection.begin()
    async_session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield async_session
    finally:
        await async_session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()
