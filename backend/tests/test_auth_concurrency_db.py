"""Penguncian login di bawah permintaan paralel (review T5.1).

Butuh beberapa koneksi sungguhan yang masing-masing commit, jadi tidak bisa
memakai fixture `session` yang di-rollback. Pengguna fiktif dibuat lalu
dihapus di akhir test (CASCADE menghapus penghitungnya), bersama catatan
`audit_logs` miliknya: `ondelete=SET NULL` tidak menghapusnya, dan tanpa ini
setiap putaran test meninggalkan jejak `user.create` di database pengembangan.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models import AuditLog, LoginThrottle, User
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
            # Audit dulu: sesudah pengguna dihapus, actor_user_id sudah menjadi NULL.
            await s.execute(
                delete(AuditLog).where(
                    or_(AuditLog.entity_id == created, AuditLog.actor_user_id == created)
                )
            )
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


async def test_penghitung_basi_dibersihkan(engine: AsyncEngine, user_id: uuid.UUID) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    async with AsyncSession(engine) as s:
        await auth._register_failure(s, settings, user_id, "10.8.8.1", now - timedelta(days=2))
        await s.commit()
    async with AsyncSession(engine) as s:
        await auth._register_failure(s, settings, user_id, "10.8.8.2", now)
        await s.commit()
        ips = set(
            (
                await s.scalars(
                    select(LoginThrottle.ip_address).where(LoginThrottle.user_id == user_id)
                )
            ).all()
        )
    assert ips == {"10.8.8.2"}
