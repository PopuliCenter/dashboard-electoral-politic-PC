"""Pencatatan berkas mentah ke data/raw/MANIFEST.csv (T1.2).

Setiap berkas di data/raw/ dicatat satu baris dengan checksum SHA-256, sumber,
URL, dan waktu pengambilan. Berkas mentah tidak pernah diubah; bila isinya
berbeda dari yang tercatat, itu galat, bukan pembaruan diam-diam.

Hanya pustaka standar, supaya bisa dijalankan di host maupun Server B.
"""

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "raw" / "MANIFEST.csv"
COLUMNS = [
    "file_path",
    "source",
    "election_year",
    "election_type",
    "region_level",
    "retrieved_at",
    "source_url",
    "sha256",
    "notes",
]


@dataclass(frozen=True)
class Entry:
    path: Path
    source: str
    retrieved_at: str
    source_url: str
    election_year: str = ""
    election_type: str = ""
    region_level: str = ""
    notes: str = ""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def record(entries: list[Entry]) -> tuple[int, int]:
    """Tambah baris baru. Berkas yang sudah tercatat dengan checksum sama dilewati.

    Mengembalikan (ditambah, dilewati). Checksum berbeda untuk path yang sama
    menaikkan galat: berkas mentah tidak boleh berubah isinya.
    """
    rows: list[dict[str, str]] = []
    if MANIFEST.exists():
        with MANIFEST.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    known = {row["file_path"]: row["sha256"] for row in rows}
    added = skipped = 0
    for entry in entries:
        key = relative(entry.path)
        digest = sha256(entry.path)
        if key in known:
            if known[key] != digest:
                raise ValueError(
                    f"{key}: checksum berbeda dari MANIFEST; berkas mentah tidak boleh "
                    "diubah, simpan sebagai berkas atau versi baru"
                )
            skipped += 1
            continue
        rows.append(
            {
                "file_path": key,
                "source": entry.source,
                "election_year": entry.election_year,
                "election_type": entry.election_type,
                "region_level": entry.region_level,
                "retrieved_at": entry.retrieved_at,
                "source_url": entry.source_url,
                "sha256": digest,
                "notes": entry.notes,
            }
        )
        known[key] = digest
        added += 1
    with MANIFEST.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return added, skipped
