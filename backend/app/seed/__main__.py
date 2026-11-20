"""Seed data referensi: kontestasi, paslon, dan partai (T2.5).

Pemakaian (di dalam kontainer api):

    python -m app.seed               # validasi lalu tulis
    python -m app.seed --dry-run     # validasi dan tampilkan perubahan, tanpa menulis

Kode keluar 0 bila berhasil, 1 bila data atau database menolak.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import get_engine, get_session_factory
from app.core.party_colors import COLORS_FILE, parse_party_colors
from app.seed.apply import ENTITIES, SeedReport, apply_reference_data
from app.seed.reference import ReferenceDataError, check_verification, load_reference_data

LABEL = {"elections": "kontestasi", "parties": "partai", "candidate_pairs": "paslon"}


def _print_report(report: SeedReport, warnings: list[str], *, dry_run: bool) -> None:
    print("Mode uji: tidak ada yang ditulis." if dry_run else "Data referensi tersimpan.")
    for entity in ENTITIES:
        print(
            f"  {LABEL[entity]:<11} baru {report.created[entity]:>3}   "
            f"diubah {report.updated[entity]:>3}   tetap {report.unchanged[entity]:>3}"
        )
    for change in report.changes:
        print(f"  * {change}")
    for warning in [*warnings, *report.warnings]:
        print(f"  ! {warning}")


async def run(data_dir: Path, *, dry_run: bool) -> int:
    settings = get_settings()
    try:
        data = load_reference_data(data_dir)
        warnings = check_verification(data, settings.app_env)
    except ReferenceDataError as exc:
        print(exc, file=sys.stderr)
        return 1

    # Warna partai (T4.5) tidak ditulis ke database, tetapi diperiksa di sini
    # supaya salah ketik terlihat dengan berkas:baris, bukan hanya di log api.
    colors = parse_party_colors(data_dir, require_verified=settings.app_env == "production")
    if colors.errors:
        print(
            f"{len(colors.errors)} masalah pada {COLORS_FILE}:\n"
            + "\n".join(f"  - {e}" for e in colors.errors),
            file=sys.stderr,
        )
        return 1

    try:
        async with get_session_factory()() as session:
            try:
                report = await apply_reference_data(session, data)
            except IntegrityError as exc:
                await session.rollback()
                print(
                    "Database menolak data referensi; tidak ada yang ditulis.\n"
                    f"  {exc.orig}\n"
                    "Penyebab yang paling mungkin: nomor urut di CSV sudah dipakai partai lain "
                    "yang ada di database tetapi tidak ada di CSV.",
                    file=sys.stderr,
                )
                return 1
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
    finally:
        await get_engine().dispose()

    _print_report(report, warnings, dry_run=dry_run)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed", description="Seed kontestasi, paslon, dan partai."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(get_settings().reference_data_dir),
        help="folder berisi parties.csv, elections.csv, candidate_pairs.csv",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="validasi dan tampilkan perubahan tanpa menulis"
    )
    args = parser.parse_args(argv)
    return asyncio.run(run(args.data_dir, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
