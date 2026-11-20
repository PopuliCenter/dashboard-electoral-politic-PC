"""Kelola pengguna dari terminal (T5.1). Dipakai untuk membuat Admin pertama.

Pemakaian (di dalam kontainer api, interaktif):

    python -m app.users create EMAIL --name "Nama Lengkap" --role admin|researcher
    python -m app.users set-password EMAIL
    python -m app.users deactivate EMAIL
    python -m app.users activate EMAIL
    python -m app.users list

Password diminta lewat prompt tersembunyi, tidak pernah lewat argumen, supaya
tidak tersimpan di riwayat shell atau terlihat di daftar proses.
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_engine, get_session_factory
from app.core.security import PasswordPolicyError, check_password_policy
from app.models import User
from app.models.enums import RoleCode
from app.services import auth


def _ask_password() -> str:
    first = getpass.getpass("Password baru: ")
    check_password_policy(first)
    if getpass.getpass("Ulangi password: ") != first:
        raise PasswordPolicyError("kedua password tidak sama")
    return first


async def _find(session: AsyncSession, email: str) -> User:
    user = await session.scalar(select(User).where(User.email == auth.normalize_email(email)))
    if user is None:
        raise LookupError(f"pengguna {email} tidak ada")
    return user


async def run(args: argparse.Namespace) -> int:
    try:
        async with get_session_factory()() as session:
            if args.command == "list":
                users = (await session.scalars(select(User).order_by(User.email))).all()
                for u in users:
                    state = "aktif" if u.is_active else "nonaktif"
                    print(f"{u.email:<40} {u.role.role_code.value:<11} {state}  {u.full_name}")
                if not users:
                    print("Belum ada pengguna.")
                return 0
            if args.command == "create":
                password = _ask_password()
                user = await auth.create_user(
                    session, args.email, args.name, password, RoleCode(args.role)
                )
                print(f"Dibuat: {user.email} ({args.role})")
            elif args.command == "set-password":
                user = await _find(session, args.email)
                await auth.set_password(session, user, _ask_password())
                print(f"Password {user.email} diganti; semua sesinya dicabut.")
            else:
                user = await _find(session, args.email)
                await auth.set_active(session, user, args.command == "activate")
                print(f"{user.email}: {'aktif' if user.is_active else 'nonaktif'}")
            await session.commit()
    except (PasswordPolicyError, ValueError, LookupError) as exc:
        print(f"Ditolak: {exc}", file=sys.stderr)
        return 1
    finally:
        await get_engine().dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.users", description="Kelola pengguna.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="buat pengguna baru")
    create.add_argument("email")
    create.add_argument("--name", required=True)
    create.add_argument("--role", required=True, choices=[r.value for r in RoleCode])
    for name in ("set-password", "deactivate", "activate"):
        sub.add_parser(name).add_argument("email")
    sub.add_parser("list", help="daftar pengguna")
    return asyncio.run(run(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
