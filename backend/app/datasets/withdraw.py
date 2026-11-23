"""Menarik baris satu versi dataset dari database (review T5.3, celah T3.4).

Dipakai bila dua dataset mengklaim sel yang sama dan manusia memutuskan yang
sudah ada harus diganti, atau bila versi yang sudah dipromosikan ternyata
salah. Hanya Admin, dan Admin itu harus mengetik passwordnya (keputusan
pengguna, review T5.3); alasan wajib; tercatat di `audit_logs`.

Yang dihapus hanya BARIS hasilnya. Baris `dataset_versions` tetap ada sebagai
riwayat, dan metadata menandainya "ditarik". Versi yang ditarik tidak bisa
dipromosikan ulang; perbaikannya dimuat sebagai versi baru.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.datasets.common import (
    WITHDRAW_ACTION,
    DatasetError,
    delete_rows,
    describe,
    version_scope,
)
from app.models import AuditLog, DatasetVersion, Role, User
from app.models.enums import RoleCode
from app.services import auth

MIN_REASON_LENGTH = 10
WITHDRAW_DENIED_ACTION = "dataset.withdraw_denied"


@dataclass(frozen=True)
class WithdrawReport:
    version_id: uuid.UUID
    dataset_name: str
    version_number: int
    scope: str
    deleted: int


async def check_admin(session: AsyncSession, user: User | None, email: str) -> User:
    if user is None:
        raise DatasetError([f"pengguna {email} tidak ada"])
    role = await session.get(Role, user.role_id)
    if not user.is_active or role is None or role.role_code is not RoleCode.ADMIN:
        raise DatasetError([f"{email} bukan Admin aktif; hanya Admin yang boleh menarik data"])
    return user


async def authorize_withdraw(
    production: AsyncSession,
    settings: Settings,
    email: str,
    password: str,
    *,
    version_id: uuid.UUID,
) -> User:
    """Password lalu peran Admin, keduanya diperiksa di produksi (tempat pengguna dikelola).

    Password diperiksa lebih dulu, dengan penghitung gagal dan penguncian yang
    sama dengan login, supaya orang tanpa password tidak bisa mengetahui apakah
    sebuah email milik Admin. Tidak melakukan commit; pemanggil wajib commit
    juga saat ditolak, supaya penghitung gagal dan jejak audit tersimpan.
    """
    try:
        user = await auth.reauthenticate(
            production,
            settings,
            email,
            password,
            channel=auth.CLI_CHANNEL,
            purpose=WITHDRAW_ACTION,
        )
    except auth.LoginError as exc:
        raise DatasetError([str(exc)]) from exc
    try:
        return await check_admin(production, user, email)
    except DatasetError:
        production.add(
            AuditLog(
                actor_user_id=user.id,
                action=WITHDRAW_DENIED_ACTION,
                entity_type="dataset_versions",
                entity_id=version_id,
                payload={"by": user.email, "reason": "not_admin"},
            )
        )
        await production.flush()
        raise


async def withdraw_version(
    session: AsyncSession,
    version_id: uuid.UUID,
    *,
    reason: str,
    actor: User | None,
    actor_email: str,
) -> WithdrawReport:
    """Hapus baris hasil satu versi dan catat alasannya. Tidak melakukan commit.

    `actor` diisi bila pengguna Admin ada di database yang sama (produksi);
    di staging, cukup emailnya yang dicatat di payload.
    """
    reason = reason.strip()
    if len(reason) < MIN_REASON_LENGTH:
        raise DatasetError([f"alasan wajib diisi, minimal {MIN_REASON_LENGTH} karakter"])
    version = await session.get(DatasetVersion, version_id)
    if version is None:
        raise DatasetError([f"versi dataset {version_id} tidak ada"])
    label = f"{version.dataset_name} v{version.version_number}"
    already = await session.scalar(
        select(AuditLog.id).where(
            AuditLog.entity_id == version_id, AuditLog.action == WITHDRAW_ACTION
        )
    )
    if already is not None:
        raise DatasetError([f"{label} sudah ditarik sebelumnya"])
    scope = await version_scope(session, version_id)
    if scope is None:
        raise DatasetError(
            [
                f"{label} tidak punya baris hasil (sudah digantikan versi lain); "
                "tidak ada yang ditarik"
            ]
        )

    deleted = await delete_rows(session, scope.kind, [version_id])
    session.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            action=WITHDRAW_ACTION,
            entity_type="dataset_versions",
            entity_id=version_id,
            payload={
                "dataset_name": version.dataset_name,
                "version_number": version.version_number,
                "scope": describe(scope),
                "deleted": deleted,
                "reason": reason,
                "by": actor_email,
            },
        )
    )
    await session.flush()
    return WithdrawReport(
        version_id, version.dataset_name, version.version_number, describe(scope), deleted
    )
