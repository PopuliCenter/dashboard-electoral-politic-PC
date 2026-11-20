"""Penguncian login di bawah permintaan paralel (review T5.1).

Butuh beberapa koneksi sungguhan yang masing-masing commit, jadi tidak bisa
memakai fixture `session` yang di-rollback. Pengguna fiktif dibuat lalu
dihapus di akhir test (CASCADE menghapus penghitungnya).
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models import LoginThrottle, User
from app.models.enums import RoleCode
from app.services import auth

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect():
            pass
    except (OSError, SQLAlchemyError) as exc:
        await engine.dispose()
        pytest.skip(f"database tidak tersedia: {type(exc).__name__}")
    yield engine
    await engine.dispose()


@pytest.fixture
async def user_id(engine: AsyncEngine) -> AsyncGenerator[uuid.UUID, None]:
    email = f"paralel-{uuid.uuid4().hex[:8]}@uji.invalid"
    async with AsyncSession(engine) as s:
        user = await auth.create_user(
            s, email, "Uji Paralel", "kata-sandi-uji-panjang", RoleCode.RESEARCHER
        )
        created = user.id  # sebelum commit: sesudahnya atribut kedaluwarsa
        await s.commit()
    try:
        yield created
    finally:
        async with AsyncSession(engine) as s:
            await s.execute(delete(User).where(User.id == created))
            await s.commit()


async def test_gagal_paralel_dari_satu_ip_tetap_mencapai_ambang(
    engine: AsyncEngine, user_id: uuid.UUID
) -> None:
    settings = get_settings()
    now = datetime.now(UTC)

    async def satu_percobaan() -> bool:
        async with AsyncSession(engine) as s:
            locked = await auth._register_failure(s, settings, user_id, "10.9.9.9", now)
            await s.commit()
            return locked

    hasil = await asyncio.gather(*(satu_percobaan() for _ in range(settings.login_max_failures)))
    # Tepat satu percobaan yang melewati ambang; tidak ada yang membaca hitungan basi.
    assert hasil.count(True) == 1

    async with AsyncSession(engine) as s:
        throttle = await s.scalar(
            select(LoginThrottle).where(
                LoginThrottle.user_id == user_id, LoginThrottle.ip_address == "10.9.9.9"
            )
        )
    assert throttle is not None and throttle.locked_until is not None
