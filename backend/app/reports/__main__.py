"""Laporan kelengkapan data (T3.5). Hanya membaca.

Pemakaian (di dalam kontainer api):

    python -m app.reports completeness [--db production|staging]
        [--election presidential:2024 ...] [--detail] [--format text|csv]
"""

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.enums import ElectionType
from app.reports.completeness import load_inputs, summarize
from app.reports.format import render_csv, render_text


def _election(value: str) -> tuple[ElectionType, int]:
    election_type, _, year = value.partition(":")
    try:
        return ElectionType(election_type), int(year)
    except ValueError as exc:
        choices = ", ".join(t.value for t in ElectionType)
        raise argparse.ArgumentTypeError(
            f"{value!r}: tulis JENIS:TAHUN, misal presidential:2024 (jenis: {choices})"
        ) from exc


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    url = settings.database_url if args.db == "production" else settings.staging_database_url
    if not url:
        print("STAGING_DATABASE_URL kosong", file=sys.stderr)
        return 1
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:
            inputs = await load_inputs(session, args.election or None)
    finally:
        await engine.dispose()

    report = summarize(inputs)
    if args.format == "csv":
        sys.stdout.write(render_csv(report))
        for warning in report.warnings:
            print(f"! {warning}", file=sys.stderr)
    else:
        sys.stdout.write(
            render_text(
                report,
                database="produksi" if args.db == "production" else "staging",
                detail=args.detail,
            )
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.reports", description="Laporan data.")
    sub = parser.add_subparsers(dest="command", required=True)
    completeness = sub.add_parser("completeness", help="kelengkapan per kontestasi dan tingkat")
    completeness.add_argument("--db", choices=("production", "staging"), default="production")
    completeness.add_argument(
        "--election", type=_election, action="append", help="JENIS:TAHUN; boleh berulang"
    )
    completeness.add_argument(
        "--detail", action="store_true", help="sebutkan wilayah yang belum lengkap"
    )
    completeness.add_argument("--format", choices=("text", "csv"), default="text")
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
