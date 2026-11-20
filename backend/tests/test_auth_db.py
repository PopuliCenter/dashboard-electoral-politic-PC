"""Login, sesi, penguncian akun, dan peran (T5.1), lewat HTTP.

Pengguna uji jelas fiktif (domain .invalid) dan hanya hidup di transaksi test
yang selalu di-rollback.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import PasswordPolicyError
from app.main import app
from app.models import AuditLog, LoginThrottle, User, UserSession
from app.models.enums import RoleCode
from app.services import auth

pytestmark = pytest.mark.integration

PASSWORD = "kata-sandi-uji-panjang"
ADMIN = "admin@uji.invalid"
PENELITI = "peneliti@uji.invalid"
COOKIE = get_settings().session_cookie_name


@pytest.fixture
async def api(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    await auth.create_user(session, ADMIN, "Admin Uji", PASSWORD, RoleCode.ADMIN)
    await auth.create_user(session, PENELITI, "Peneliti Uji", PASSWORD, RoleCode.RESEARCHER)

    async def override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_session, None)


async def _login(api: AsyncClient, email: str = PENELITI, password: str = PASSWORD) -> int:
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": password})
    return response.status_code


async def _user(session: AsyncSession, email: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


# --------------------------------------------------------------------------- #
# Login dan sesi
# --------------------------------------------------------------------------- #


async def test_login_memberi_cookie_aman_dan_membuka_data(api: AsyncClient) -> None:
    assert (await api.get("/api/v1/elections")).status_code == 401
    response = await api.post(
        "/api/v1/auth/login", json={"email": " Peneliti@UJI.invalid ", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "researcher"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie

    assert (await api.get("/api/v1/auth/me")).json()["email"] == PENELITI
    assert (await api.get("/api/v1/elections")).status_code == 200


async def test_health_tetap_publik(api: AsyncClient) -> None:
    assert (await api.get("/api/v1/health/live")).status_code == 200


async def test_database_hanya_menyimpan_hash_token(api: AsyncClient, session: AsyncSession) -> None:
    await _login(api)
    token = api.cookies[COOKIE]
    stored = (await session.scalars(select(UserSession.token_hash))).all()
    assert token not in stored and len(stored) >= 1


async def test_pesan_gagal_sama_untuk_email_tak_dikenal_dan_password_salah(
    api: AsyncClient, session: AsyncSession
) -> None:
    unknown = await api.post(
        "/api/v1/auth/login", json={"email": "tidak-ada@uji.invalid", "password": PASSWORD}
    )
    wrong = await api.post("/api/v1/auth/login", json={"email": PENELITI, "password": "salah"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    actions = (
        await session.scalars(select(AuditLog.action).where(AuditLog.action.like("auth.%")))
    ).all()
    assert actions.count("auth.login_failed") >= 2


async def test_logout_mencabut_sesi(api: AsyncClient) -> None:
    await _login(api)
    token = api.cookies[COOKIE]
    assert (await api.post("/api/v1/auth/logout")).status_code == 204
    api.cookies.set(COOKIE, token)  # pakai ulang token lama
    assert (await api.get("/api/v1/auth/me")).status_code == 401


async def test_sesi_idle_dan_batas_absolut_berakhir(
    api: AsyncClient, session: AsyncSession
) -> None:
    await _login(api)
    user_session = await session.scalar(
        select(UserSession).order_by(UserSession.created_at.desc()).limit(1)
    )
    assert user_session is not None
    user_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()
    assert (await api.get("/api/v1/auth/me")).status_code == 401

    await _login(api)
    newest = await session.scalar(
        select(UserSession).order_by(UserSession.created_at.desc()).limit(1)
    )
    assert newest is not None
    newest.created_at = datetime.now(UTC) - timedelta(hours=get_settings().session_absolute_hours)
    await session.flush()
    assert (await api.get("/api/v1/auth/me")).status_code == 401


# --------------------------------------------------------------------------- #
# Penguncian dan status akun
# --------------------------------------------------------------------------- #


def _dari_ip(ip: str) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, client=(ip, 50000)), base_url="http://test")


async def _throttle(session: AsyncSession, email: str, ip: str) -> LoginThrottle | None:
    user = await _user(session, email)
    return await session.get(LoginThrottle, (user.id, ip))


async def test_akun_dikunci_per_ip_setelah_gagal_berulang(
    api: AsyncClient, session: AsyncSession
) -> None:
    settings = get_settings()
    async with _dari_ip("10.0.0.1") as penyerang, _dari_ip("10.0.0.2") as pemilik:
        for _ in range(settings.login_max_failures):
            assert await _login(penyerang, password="salah-terus") == 401
        # Dari IP penyerang, password benar pun ditolak selama terkunci...
        assert await _login(penyerang) == 401
        # ...tetapi pemilik akun dari IP lain tetap bisa masuk (keputusan pengguna).
        assert await _login(pemilik) == 200

        throttle = await _throttle(session, PENELITI, "10.0.0.1")
        assert throttle is not None and throttle.locked_until is not None
        throttle.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.flush()
        assert await _login(penyerang) == 200
        # Login berhasil menghapus penghitung IP itu.
        session.expire_all()
        assert await _throttle(session, PENELITI, "10.0.0.1") is None


async def test_ganti_password_menghapus_penguncian(api: AsyncClient, session: AsyncSession) -> None:
    async with _dari_ip("10.0.0.3") as klien:
        for _ in range(get_settings().login_max_failures):
            await _login(klien, password="salah-terus")
        await auth.set_password(
            session, await _user(session, PENELITI), "password-baru-yang-panjang"
        )
        assert await _login(klien, password="password-baru-yang-panjang") == 200


async def test_dokumentasi_api_hanya_di_pengembangan(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app

    try:
        monkeypatch.setenv("APP_ENV", "production")
        get_settings.cache_clear()
        produksi = create_app()
        async with AsyncClient(transport=ASGITransport(app=produksi), base_url="http://test") as c:
            for path in ("/docs", "/redoc", "/openapi.json"):
                assert (await c.get(path)).status_code == 404
    finally:
        monkeypatch.delenv("APP_ENV", raising=False)
        get_settings.cache_clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/openapi.json")).status_code == 200


async def test_akun_nonaktif_tidak_bisa_login_dan_sesinya_dicabut(
    api: AsyncClient, session: AsyncSession
) -> None:
    await _login(api)
    assert (await api.get("/api/v1/auth/me")).status_code == 200
    await auth.set_active(session, await _user(session, PENELITI), False)
    assert (await api.get("/api/v1/auth/me")).status_code == 401
    assert await _login(api) == 401


async def test_ganti_password_mencabut_semua_sesi(api: AsyncClient, session: AsyncSession) -> None:
    await _login(api)
    await auth.set_password(session, await _user(session, PENELITI), "password-baru-yang-panjang")
    assert (await api.get("/api/v1/auth/me")).status_code == 401
    assert await _login(api) == 401
    assert await _login(api, password="password-baru-yang-panjang") == 200


# --------------------------------------------------------------------------- #
# Peran dan asal permintaan
# --------------------------------------------------------------------------- #


async def test_peran_admin_dan_peneliti(session: AsyncSession, api: AsyncClient) -> None:
    probe = FastAPI()

    @probe.get("/khusus-admin")
    async def khusus_admin(user: User = Depends(require_admin)) -> dict[str, str]:
        return {"email": user.email}

    async def override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    probe.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=probe), base_url="http://test") as c:
        assert (await c.get("/khusus-admin")).status_code == 401
        for email, expected in ((PENELITI, 403), (ADMIN, 200)):
            await _login(api, email)
            c.cookies.set(COOKIE, api.cookies[COOKIE])
            assert (await c.get("/khusus-admin")).status_code == expected


async def test_post_dari_situs_lain_ditolak(api: AsyncClient) -> None:
    body = {"email": PENELITI, "password": PASSWORD}
    asing = await api.post(
        "/api/v1/auth/login", json=body, headers={"Origin": "https://jahat.invalid"}
    )
    assert asing.status_code == 403
    sah = await api.post(
        "/api/v1/auth/login", json=body, headers={"Origin": get_settings().cors_origin_list[0]}
    )
    assert sah.status_code == 200


# --------------------------------------------------------------------------- #
# Pembuatan pengguna
# --------------------------------------------------------------------------- #


async def test_aturan_pembuatan_pengguna(session: AsyncSession, api: AsyncClient) -> None:
    with pytest.raises(PasswordPolicyError):
        await auth.create_user(session, "baru@uji.invalid", "Baru", "pendek", RoleCode.RESEARCHER)
    with pytest.raises(ValueError, match="sudah ada"):
        await auth.create_user(session, PENELITI.upper(), "Ganda", PASSWORD, RoleCode.RESEARCHER)
    with pytest.raises(ValueError, match="tidak sah"):
        await auth.create_user(session, "bukan-email", "X", PASSWORD, RoleCode.RESEARCHER)
