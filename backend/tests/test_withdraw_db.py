"""Penarikan versi dataset meminta password Admin (keputusan pengguna, review T5.3).

Memakai ulang fixture dua database dari test T3.4. Semua perubahan di-rollback.
"""

# Fixture `dua_db` dipakai ulang dari test_datasets_db; ruff mengira parameter
# bernama sama sebagai definisi ulang.
# ruff: noqa: F811

import argparse
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.datasets import __main__ as cli
from app.datasets.common import WITHDRAW_ACTION, DatasetError
from app.datasets.withdraw import WITHDRAW_DENIED_ACTION, authorize_withdraw
from app.models import AuditLog, ElectionResult, LoginThrottle, User
from app.models.enums import RoleCode
from app.services import auth
from tests.test_datasets_db import _dpr, _muat, dua_db  # noqa: F401

pytestmark = pytest.mark.integration

PASSWORD = "kata-sandi-uji-panjang"
VERSI = uuid.UUID(int=0)


async def _pengguna(db: AsyncSession, email: str, role: RoleCode) -> User:
    return await auth.create_user(db, email, "Pengguna Uji", PASSWORD, role)


async def _audit(db: AsyncSession, action: str, user: User | None = None) -> list[AuditLog]:
    query = select(AuditLog).where(AuditLog.action == action)
    if user is not None:
        query = query.where(AuditLog.actor_user_id == user.id)
    return list((await db.scalars(query)).all())


async def _throttle(db: AsyncSession, user: User) -> LoginThrottle | None:
    return await db.scalar(
        select(LoginThrottle).where(
            LoginThrottle.user_id == user.id, LoginThrottle.ip_address == auth.CLI_CHANNEL
        )
    )


async def test_password_salah_ditolak_dihitung_dan_dicatat(
    dua_db: tuple[AsyncSession, AsyncSession],
) -> None:
    _, produksi = dua_db
    admin = await _pengguna(produksi, "admin-tarik@uji.invalid", RoleCode.ADMIN)
    with pytest.raises(DatasetError, match="email atau password salah"):
        await authorize_withdraw(
            produksi, get_settings(), admin.email, "bukan-passwordnya", version_id=VERSI
        )
    (gagal,) = await _audit(produksi, "auth.reauth_failed", admin)
    assert gagal.payload == {
        "channel": auth.CLI_CHANNEL,
        "purpose": WITHDRAW_ACTION,
        "reason": "wrong_password",
    }
    throttle = await _throttle(produksi, admin)
    assert throttle is not None and throttle.failed_count == 1

    # Password benar: lolos, penghitung CLI dihapus, konfirmasinya tercatat.
    assert (
        await authorize_withdraw(produksi, get_settings(), admin.email, PASSWORD, version_id=VERSI)
    ).id == admin.id
    assert await _throttle(produksi, admin) is None
    assert len(await _audit(produksi, "auth.reauth", admin)) == 1


async def test_terkunci_setelah_batas_gagal_walau_password_benar(
    dua_db: tuple[AsyncSession, AsyncSession],
) -> None:
    _, produksi = dua_db
    settings = get_settings()
    admin = await _pengguna(produksi, "admin-kunci@uji.invalid", RoleCode.ADMIN)
    for _ in range(settings.login_max_failures):
        with pytest.raises(DatasetError):
            await authorize_withdraw(produksi, settings, admin.email, "salah", version_id=VERSI)
    with pytest.raises(DatasetError):
        await authorize_withdraw(produksi, settings, admin.email, PASSWORD, version_id=VERSI)
    alasan = [a.payload["reason"] for a in await _audit(produksi, "auth.reauth_failed", admin)]
    assert alasan[-2:] == ["wrong_password_locked", "locked"]


async def test_peneliti_dengan_password_benar_tetap_ditolak(
    dua_db: tuple[AsyncSession, AsyncSession],
) -> None:
    _, produksi = dua_db
    peneliti = await _pengguna(produksi, "peneliti-tarik2@uji.invalid", RoleCode.RESEARCHER)
    with pytest.raises(DatasetError, match="bukan Admin"):
        await authorize_withdraw(
            produksi, get_settings(), peneliti.email, PASSWORD, version_id=VERSI
        )
    (ditolak,) = await _audit(produksi, WITHDRAW_DENIED_ACTION, peneliti)
    assert ditolak.entity_id == VERSI and ditolak.payload["reason"] == "not_admin"


async def test_email_tak_dikenal_ditolak_dengan_pesan_yang_sama(
    dua_db: tuple[AsyncSession, AsyncSession],
) -> None:
    _, produksi = dua_db
    with pytest.raises(DatasetError, match="email atau password salah"):
        await authorize_withdraw(
            produksi, get_settings(), "hantu-tarik@uji.invalid", PASSWORD, version_id=VERSI
        )


async def test_perintah_tarik_meminta_password_sebelum_menyentuh_data(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging, produksi = dua_db
    admin = await _pengguna(produksi, "admin-cli@uji.invalid", RoleCode.ADMIN)
    hasil = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    assert hasil.version is not None
    version_id = hasil.version.id
    production_url = get_settings().database_url

    @asynccontextmanager
    async def sesi_uji(url: str) -> AsyncIterator[AsyncSession]:
        # Sesi fixture: commit di sini tidak menembus transaksi luar yang di-rollback.
        yield produksi if url == production_url else staging

    monkeypatch.setattr(cli, "_session", sesi_uji)
    args = argparse.Namespace(
        version_id=version_id,
        by=admin.email,
        reason="uji penarikan lewat perintah",
        db="staging",
        dry_run=False,
    )

    async def baris_versi() -> int:
        return (
            await staging.scalar(
                select(func.count())
                .select_from(ElectionResult)
                .where(ElectionResult.dataset_version_id == version_id)
            )
        ) or 0

    diminta: list[str] = []

    def password_salah(prompt: str) -> str:
        diminta.append(prompt)
        return "bukan-passwordnya"

    monkeypatch.setattr(cli.getpass, "getpass", password_salah)
    assert await cli.run_withdraw(args) == 1
    assert diminta == [f"Password Admin {admin.email}: "]
    assert await baris_versi() == 1  # data staging tidak tersentuh

    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: PASSWORD)
    assert await cli.run_withdraw(args) == 0
    assert await baris_versi() == 0
    (tarik,) = await _audit(staging, WITHDRAW_ACTION)
    assert tarik.payload["by"] == admin.email
