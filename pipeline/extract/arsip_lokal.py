"""Arsipkan berkas yang sudah ada di disk (unduhan manual, Google Drive, PPID) ke data/raw/ (T1.2).

Untuk dokumen yang tidak diunduh oleh skrip: berkas diserahkan pengguna, hasil
permohonan PPID, atau unduhan manual dari Google Drive. Berkas disalin apa adanya
(isi tidak diubah, nama dipertahankan) lalu dicatat di data/raw/MANIFEST.csv.

- Berkas yang sudah ada di tujuan dengan isi sama dilewati.
- Berkas yang sudah ada dengan isi berbeda ditolak: simpan sebagai berkas baru.
- `retrieved_at` diisi waktu berkas sumber terakhir diubah di disk (waktu ia
  diterima), bukan waktu pengarsipan. Asal berkas wajib ditulis di --origin;
  bila URL asalnya tidak diketahui, tulis itu apa adanya, jangan ditebak.

Pemakaian (dari akar repo, Python 3.11+, hanya pustaka standar):

    python pipeline/extract/arsip_lokal.py BERKAS... --dest data/raw/<sumber>/<tahun> \\
        --source "Penerbit: nama dokumen" --origin "URL atau 'diserahkan pengguna'" \\
        [--election-year 2024] [--election-type legislative_dpr] [--region-level district] \\
        [--notes "..."]
"""

import argparse
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import manifest

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
TYPES = ("presidential", "legislative_dpr", "legislative_dprd_province")
LEVELS = ("province", "regency", "district")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--dest", required=True, type=Path, help="folder di bawah data/raw/")
    parser.add_argument("--source", required=True, help="penerbit dan nama dokumen")
    parser.add_argument("--origin", required=True, help="URL asal, atau keterangan bila tidak ada")
    parser.add_argument("--election-year", default="")
    parser.add_argument("--election-type", default="", choices=("", *TYPES))
    parser.add_argument("--region-level", default="", choices=("", *LEVELS))
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    dest = (ROOT / args.dest).resolve() if not args.dest.is_absolute() else args.dest.resolve()
    if RAW.resolve() not in dest.parents and dest != RAW.resolve():
        sys.exit(f"--dest harus di bawah {RAW.relative_to(ROOT)}")
    entries = []
    for source in args.files:
        if not source.is_file():
            sys.exit(f"bukan berkas: {source}")
        target = dest / source.name
        if target.exists():
            if manifest.sha256(target) != manifest.sha256(source):
                existing = target.relative_to(ROOT)
                sys.exit(f"{existing} sudah ada dengan isi berbeda; simpan dengan nama lain")
        else:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            print(f"{target.relative_to(ROOT)} ({target.stat().st_size} byte)")
        received = datetime.fromtimestamp(source.stat().st_mtime, UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        entries.append(
            manifest.Entry(
                path=target,
                source=args.source,
                retrieved_at=received,
                source_url=args.origin,
                election_year=args.election_year,
                election_type=args.election_type,
                region_level=args.region_level,
                notes=args.notes,
            )
        )
    added, skipped = manifest.record(entries)
    print(f"MANIFEST: {added} ditambah, {skipped} sudah tercatat")


if __name__ == "__main__":
    main()
