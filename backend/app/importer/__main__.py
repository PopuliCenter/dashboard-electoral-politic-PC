"""Validasi berkas impor baku terhadap data referensi di database (T3.1).

Pemakaian (di dalam kontainer api):

    python -m app.importer BERKAS.csv [BERKAS.csv ...]

Hanya membaca; tidak ada yang ditulis ke database. Kode keluar 0 bila semua
berkas lolos, 1 bila ada yang gagal.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.database import get_engine, get_session_factory
from app.importer.catalog import load_catalog
from app.importer.format import LABEL
from app.importer.validator import ValidationReport, validate_file

# Ribuan galat yang sama tidak membantu siapa pun; sisanya cukup dihitung.
MAX_ERRORS_PRINTED = 100


def _print_report(report: ValidationReport) -> None:
    verdict = "LOLOS" if report.passed else "GAGAL"
    print(f"{report.file_name}: {verdict}")
    if report.kind is not None:
        print(f"  jenis        {LABEL[report.kind]}")
    if report.election is not None:
        election_type, year = report.election
        print(f"  kontestasi   {election_type.value} {year}")
    if report.data_status is not None:
        print(f"  data_status  {report.data_status.value}")
    if report.passed:
        print(f"  baris        {len(report.records)}")
    if report.checksum:
        print(f"  sha256       {report.checksum}")
    for error in report.errors[:MAX_ERRORS_PRINTED]:
        print(f"  x {error}")
    if len(report.errors) > MAX_ERRORS_PRINTED:
        print(f"  x ... dan {len(report.errors) - MAX_ERRORS_PRINTED} kesalahan lain")
    for warning in report.warnings[:MAX_ERRORS_PRINTED]:
        print(f"  ! {warning}")
    if len(report.warnings) > MAX_ERRORS_PRINTED:
        print(f"  ! ... dan {len(report.warnings) - MAX_ERRORS_PRINTED} peringatan lain")


async def run(paths: list[Path]) -> int:
    try:
        async with get_session_factory()() as session:
            catalog = await load_catalog(session)
    finally:
        await get_engine().dispose()

    reports = [validate_file(path, catalog) for path in paths]
    for report in reports:
        _print_report(report)
    return 0 if all(r.passed for r in reports) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.importer",
        description="Validasi berkas impor baku (CSV) tanpa menulis ke database.",
    )
    parser.add_argument("files", nargs="+", type=Path, help="berkas CSV format impor baku")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.files))


if __name__ == "__main__":
    sys.exit(main())
