"""Login, sesi, dan penguncian akun (T5.1).

Fungsi di sini tidak melakukan commit; pemanggil (endpoint) yang melakukannya.
Setiap login, berhasil maupun gagal, dicatat di `audit_logs` tanpa password.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    check_password_policy,
    hash_password_async,
    hash_session_token,
    needs_rehash,
    new_session_token,
    verify_password_async,
)
from app.models import AuditLog, LoginThrottle, Role, User, UserSession
from app.models.enums import RoleCode

# Pesan tunggal untuk semua kegagalan login: tidak membedakan email tak terdaftar,
# password salah, akun nonaktif, atau akun terkunci.
LOGIN_FAILED = "email atau password salah, atau akun sedang dikunci sementara"

# Sesi aktif tidak ditulis ulang pada setiap permintaan; cukup sekali per menit.
LAST_SEEN_RESOLUTION = timedelta(minutes=1)


class LoginError(Exception):
    pass


@dataclass(frozen=True)
class LoginResult:
    user: User
    token: str
    expires_at: datetime


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    return datetime.now(UTC)


# Kunci penghitung bila alamat IP tidak diketahui. Di belakang Nginx alamat asli
# wajib diteruskan (T6.1); tanpa itu semua permintaan tampak dari satu IP dan
# penguncian per akun+IP berperilaku seperti per akun saja.
UNKNOWN_IP = "unknown"

# Penghitung gagal yang tidak tersentuh selama ini (dan tidak terkunci) dibuang.
STALE_THROTTLE_AGE = timedelta(days=1)


async def _locked_until(
    session: AsyncSession, user_id: uuid.UUID, ip: str, now: datetime
) -> datetime | None:
    locked = await session.scalar(
        select(LoginThrottle.locked_until).where(
            LoginThrottle.user_id == user_id, LoginThrottle.ip_address == ip
        )
    )
    return locked if locked is not None and locked > now else None


async def _register_failure(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID, ip: str, now: datetime
) -> bool:
    """Naikkan penghitung gagal (pengguna, IP) secara atomik. True bila kini terkunci.

    Satu pernyataan INSERT ... ON CONFLICT DO UPDATE ... RETURNING: permintaan
    paralel tidak bisa membaca hitungan yang sama lalu sama-sama lolos ambang.
    Penguncian yang sudah kedaluwarsa memulai hitungan dari 1 lagi.
    """
    # Bersihkan penghitung basi akun ini (tidak terkunci, tak tersentuh sehari),
    # supaya percobaan dari banyak IP tidak menumpuk baris tanpa batas.
    await session.execute(
        delete(LoginThrottle).where(
            LoginThrottle.user_id == user_id,
            LoginThrottle.updated_at < now - STALE_THROTTLE_AGE,
            or_(LoginThrottle.locked_until.is_(None), LoginThrottle.locked_until < now),
        )
    )
    table = LoginThrottle.__table__
    base = insert(LoginThrottle).values(
        user_id=user_id, ip_address=ip, failed_count=1, locked_until=None, updated_at=now
    )
    expired = table.c.locked_until.is_not(None) & (table.c.locked_until <= now)
    stmt = base.on_conflict_do_update(
        index_elements=[table.c.user_id, table.c.ip_address],
        set_={
            "failed_count": case((expired, 1), else_=table.c.failed_count + 1),
            "locked_until": case((expired, None), else_=table.c.locked_until),
            "updated_at": now,
        },
    ).returning(table.c.failed_count)
    count = (await session.execute(stmt)).scalar_one()
    if count < settings.login_max_failures:
        return False
    await session.execute(
        update(LoginThrottle)
        .where(LoginThrottle.user_id == user_id, LoginThrottle.ip_address == ip)
        .values(
            locked_until=now + timedelta(minutes=settings.login_lock_minutes),
            failed_count=0,
            updated_at=now,
        )
    )
    return True


async def clear_throttles(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(LoginThrottle).where(LoginThrottle.user_id == user_id))


async def login(
    session: AsyncSession,
    settings: Settings,
    email: str,
    password: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> LoginResult:
    now = _now()
    ip = ip_address or UNKNOWN_IP
    normalized = normalize_email(email)
    user = await session.scalar(select(User).where(User.email == normalized))

    if user is None:
        await verify_password_async(password, DUMMY_PASSWORD_HASH)  # samakan waktu respons
        await _audit(session, "auth.login_failed", None, ip_address, {"reason": "unknown_email"})
        raise LoginError(LOGIN_FAILED)

    if await _locked_until(session, user.id, ip, now) is not None:
        await verify_password_async(password, DUMMY_PASSWORD_HASH)
        await _audit(session, "auth.login_failed", user.id, ip_address, {"reason": "locked"})
        raise LoginError(LOGIN_FAILED)

    password_ok = await verify_password_async(password, user.password_hash)
    if not password_ok or not user.is_active:
        reason = "inactive" if not user.is_active else "wrong_password"
        if reason == "wrong_password" and await _register_failure(
            session, settings, user.id, ip, now
        ):
            reason = "wrong_password_locked"
        await _audit(session, "auth.login_failed", user.id, ip_address, {"reason": reason})
        raise LoginError(LOGIN_FAILED)

    await session.execute(
        delete(LoginThrottle).where(
            LoginThrottle.user_id == user.id, LoginThrottle.ip_address == ip
        )
    )
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = await hash_password_async(password)

    token = new_session_token()
    expires_at = now + timedelta(minutes=settings.session_idle_minutes)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    await _audit(session, "auth.login", user.id, ip_address, None)
    await session.flush()
    return LoginResult(user, token, expires_at)


async def resolve_session(
    session: AsyncSession, settings: Settings, token: str | None
) -> UserSession | None:
    """Sesi yang masih berlaku untuk token ini, dengan batas idle diperpanjang."""
    if not token:
        return None
    now = _now()
    found = await session.scalar(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    )
    if found is None or found.revoked_at is not None or found.expires_at <= now:
        return None
    absolute_limit = found.created_at + timedelta(hours=settings.session_absolute_hours)
    if now >= absolute_limit or not found.user.is_active:
        return None
    if now - found.last_seen_at >= LAST_SEEN_RESOLUTION:
        found.last_seen_at = now
        found.expires_at = min(
            now + timedelta(minutes=settings.session_idle_minutes), absolute_limit
        )
        await session.flush()
    return found


async def logout(session: AsyncSession, user_session: UserSession, ip_address: str | None) -> None:
    user_session.revoked_at = _now()
    await _audit(session, "auth.logout", user_session.user_id, ip_address, None)
    await session.flush()


async def revoke_all_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def create_user(
    session: AsyncSession, email: str, full_name: str, password: str, role: RoleCode
) -> User:
    check_password_policy(password)
    normalized = normalize_email(email)
    if "@" not in normalized:
        raise ValueError(f"email {email!r} tidak sah")
    if await session.scalar(select(User.id).where(User.email == normalized)):
        raise ValueError(f"pengguna {normalized} sudah ada")
    role_row = await session.scalar(select(Role).where(Role.role_code == role))
    if role_row is None:
        raise ValueError(f"peran {role.value} belum ada; jalankan migrasi")
    user = User(
        email=normalized,
        full_name=full_name.strip(),
        password_hash=await hash_password_async(password),
        role_id=role_row.id,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await _audit(session, "user.create", user.id, None, {"role": role.value})
    return user


async def set_password(session: AsyncSession, user: User, password: str) -> None:
    """Ganti password dan cabut semua sesi pengguna itu."""
    check_password_policy(password)
    user.password_hash = await hash_password_async(password)
    await clear_throttles(session, user.id)
    await revoke_all_sessions(session, user.id)
    await _audit(session, "user.set_password", user.id, None, None)
    await session.flush()


async def set_active(session: AsyncSession, user: User, active: bool) -> None:
    user.is_active = active
    if not active:
        await revoke_all_sessions(session, user.id)
    await _audit(session, "user.activate" if active else "user.deactivate", user.id, None, None)
    await session.flush()


async def _audit(
    session: AsyncSession,
    action: str,
    user_id: uuid.UUID | None,
    ip_address: str | None,
    payload: dict[str, object] | None,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=user_id,
            action=action,
            entity_type="users",
            entity_id=user_id,
            payload=payload,
            ip_address=ip_address,
        )
    )
