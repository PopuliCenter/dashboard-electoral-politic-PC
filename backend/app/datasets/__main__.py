"""Muat ke staging dan promosi ke produksi (T3.4).

Pemakaian (di dalam kontainer api):

    python -m app.datasets load BERKAS.csv --dataset NAMA --source-name NAMA \\
        [--source-type T --source-url U --collection-method M --retrieved-at YYYY-MM-DD]
    python -m app.datasets list
    python -m app.datasets promote VERSION_ID [--dry-run]
    python -m app.datasets withdraw VERSION_ID --by EMAIL_ADMIN --reason "..." \\
        [--db production|staging] [--dry-run]

`load` hanya menulis ke STAGING_DATABASE_URL. `promote` membaca staging dan
menulis ke DATABASE_URL. Keduanya menolak jalan bila kedua URL kosong atau sama.
Kode keluar 0 bila berhasil, 1 bila ditolak.
"""

import argparse
import asyncio
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.datasets.common import DatasetError, describe, version_scope
from app.datasets.promotion import promote_version, promotion_audit
from app.datasets.staging import SourceInfo, load_into_staging
from app.datasets.withdraw import check_admin, withdraw_version
from app.importer.catalog import load_catalog
from app.importer.validator import validate_file
from app.models import DatasetVersion, User
from app.services.auth import normalize_email


class ConfigError(Exception):
    pass


def _urls() -> tuple[str, str]:
    settings = get_settings()
    staging = settings.staging_database_url
    if not staging:
        raise ConfigError("STAGING_DATABASE_URL kosong; data baru selalu masuk staging dulu")
    if staging == settings.database_url:
        raise ConfigError(
            "STAGING_DATABASE_URL sama dengan DATABASE_URL; staging harus database terpisah"
        )
    return staging, settings.database_url


@asynccontextmanager
async def _session(url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
    finally:
        await engine.dispose()


def _print_problems(title: str, errors: list[str]) -> None:
    print(title, file=sys.stderr)
    for error in errors:
        print(f"  x {error}", file=sys.stderr)


async def run_load(args: argparse.Namespace) -> int:
    staging_url, _ = _urls()
    source = SourceInfo(
        source_name=args.source_name,
        source_type=args.source_type,
        source_url=args.source_url,
        collection_method=args.collection_method,
        retrieved_at=(
            datetime.combine(args.retrieved_at, datetime.min.time(), tzinfo=UTC)
            if args.retrieved_at
            else None
        ),
    )
    async with _session(staging_url) as session:
        report = validate_file(args.file, await load_catalog(session))
        try:
            result = await load_into_staging(
                session,
                report,
                dataset_name=args.dataset,
                source=source,
                file_reference=args.file.name,
            )
        except DatasetError as exc:
            await session.rollback()
            _print_problems("Muat ke staging ditolak; tidak ada yang ditulis.", exc.errors)
            return 1
        await session.commit()

    for warning in result.warnings:
        print(f"  ! {warning}")
    if result.version is None:
        _print_problems(
            f"{args.file.name}: GAGAL validasi; percobaan dicatat, tidak ada versi dataset.",
            result.errors,
        )
        return 1
    print(
        f"{args.file.name}: dimuat ke staging sebagai {result.version.dataset_name} "
        f"v{result.version.version_number} ({result.record_count} baris)\n"
        f"  version_id {result.version.id}\n"
        "  status pending: promosi ditahan sampai rekonsiliasi (T3.3) lolos"
    )
    return 0


async def run_list(_: argparse.Namespace) -> int:
    staging_url, production_url = _urls()
    async with _session(production_url) as production:
        promoted = set((await production.scalars(select(DatasetVersion.id))).all())
    async with _session(staging_url) as staging:
        versions = (
            await staging.scalars(
                select(DatasetVersion).order_by(
                    DatasetVersion.dataset_name, DatasetVersion.version_number
                )
            )
        ).all()
        if not versions:
            print("Staging belum berisi versi dataset.")
        for v in versions:
            scope = await version_scope(staging, v.id)
            where = "produksi" if v.id in promoted else "staging"
            print(
                f"{v.id}  {v.dataset_name} v{v.version_number}  "
                f"{describe(scope) if scope else '-'}  {v.data_status.value}  "
                f"{v.validation_status.value}  {v.record_count} baris  [{where}]"
            )
    return 0


async def run_promote(args: argparse.Namespace) -> int:
    staging_url, production_url = _urls()
    async with _session(staging_url) as staging, _session(production_url) as production:
        try:
            report = await promote_version(staging, production, args.version_id)
        except DatasetError as exc:
            await production.rollback()
            _print_problems("Promosi ditolak; produksi tidak berubah.", exc.errors)
            return 1
        if args.dry_run:
            await production.rollback()
        else:
            # Produksi dulu. Bila commit staging gagal sesudahnya, yang hilang
            # hanya catatan audit di staging; data produksi tetap utuh.
            await production.commit()
            staging.add(promotion_audit(report))
            await staging.commit()

    print("Mode uji: produksi tidak diubah." if args.dry_run else "Dipromosikan ke produksi.")
    print(f"  {report.dataset_name} v{report.version_number}  {report.scope}")
    print(f"  baris masuk     {report.inserted}")
    for warning in report.warnings:
        print(f"  ! {warning}")
    if report.replaced_versions:
        versions = ", ".join(f"v{n}" for n in report.replaced_versions)
        print(f"  baris diganti   {report.replaced} (dari {versions})")
    return 0


async def run_withdraw(args: argparse.Namespace) -> int:
    staging_url, production_url = _urls()
    # Admin selalu diperiksa di produksi: di sanalah pengguna dikelola.
    async with _session(production_url) as production:
        user = await production.scalar(select(User).where(User.email == normalize_email(args.by)))
        try:
            admin = await check_admin(production, user, args.by)
        except DatasetError as exc:
            _print_problems("Penarikan ditolak.", exc.errors)
            return 1

    target = production_url if args.db == "production" else staging_url
    async with _session(target) as session:
        try:
            report = await withdraw_version(
                session,
                args.version_id,
                reason=args.reason,
                actor=admin if args.db == "production" else None,
                actor_email=admin.email,
            )
        except DatasetError as exc:
            await session.rollback()
            _print_problems("Penarikan ditolak; tidak ada yang berubah.", exc.errors)
            return 1
        if args.dry_run:
            await session.rollback()
        else:
            await session.commit()

    print("Mode uji: tidak ada yang berubah." if args.dry_run else f"Ditarik dari {args.db}.")
    print(f"  {report.dataset_name} v{report.version_number}  {report.scope}")
    print(f"  baris dihapus   {report.deleted}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.datasets", description="Muat ke staging dan promosi ke produksi."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    load = sub.add_parser("load", help="validasi lalu muat satu berkas ke staging")
    load.add_argument("file", type=Path)
    load.add_argument("--dataset", required=True, help="nama dataset, misal kpu-dpr-2024-kecamatan")
    load.add_argument("--source-name", required=True, help="nama dokumen sumber")
    load.add_argument("--source-type", help="misal kpu_rekapitulasi; wajib untuk sumber baru")
    load.add_argument("--source-url")
    load.add_argument("--collection-method", help="misal ekstraksi_pdf, ketik_manual")
    load.add_argument(
        "--retrieved-at",
        type=lambda value: datetime.strptime(value, "%Y-%m-%d").date(),
        help="tanggal dokumen diunduh, YYYY-MM-DD",
    )
    load.set_defaults(handler=run_load)

    listing = sub.add_parser("list", help="daftar versi dataset di staging")
    listing.set_defaults(handler=run_list)

    promote = sub.add_parser("promote", help="promosikan satu versi ke produksi")
    promote.add_argument("version_id", type=uuid.UUID)
    promote.add_argument("--dry-run", action="store_true", help="periksa tanpa menulis")
    promote.set_defaults(handler=run_promote)

    withdraw = sub.add_parser(
        "withdraw", help="tarik baris satu versi (Admin, alasan wajib, tercatat di audit)"
    )
    withdraw.add_argument("version_id", type=uuid.UUID)
    withdraw.add_argument("--by", required=True, help="email Admin yang menarik")
    withdraw.add_argument("--reason", required=True, help="alasan penarikan")
    withdraw.add_argument("--db", choices=("production", "staging"), default="production")
    withdraw.add_argument("--dry-run", action="store_true", help="periksa tanpa menulis")
    withdraw.set_defaults(handler=run_withdraw)

    args = parser.parse_args(argv)
    try:
        return asyncio.run(args.handler(args))
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
