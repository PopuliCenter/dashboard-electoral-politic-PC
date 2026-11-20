"""Pembaca CSV bersama untuk berkas yang disunting manusia (seed T2.5, impor T3.1).

Menerima dua kebiasaan Excel: BOM UTF-8 di awal berkas, dan titik koma sebagai
pemisah kolom (bawaan Excel berlokal Indonesia, karena koma dipakai sebagai
pemisah desimal). Kesalahan tidak dilempar, tetapi ditambahkan ke daftar
`errors` supaya pemanggil bisa melaporkan semuanya sekaligus.
"""

import csv
import hashlib
import io
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CsvTable:
    name: str
    columns: tuple[str, ...]
    # (nomor baris di berkas, isi baris). Baris kosong sudah dibuang.
    rows: tuple[tuple[int, dict[str, str]], ...]
    checksum: str


def read_csv(path: Path, errors: list[str]) -> CsvTable | None:
    """Baca berkas. Kembalikan None bila berkas tidak bisa dibaca sama sekali.

    Checksum SHA-256 dihitung dari byte asli berkas, sebelum pembacaan apa pun.
    """
    if not path.is_file():
        errors.append(f"{path.name}: berkas tidak ditemukan di {path.parent}")
        return None

    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        errors.append(
            f"{path.name}: bukan UTF-8. Di Excel, simpan dengan format "
            "'CSV UTF-8 (Comma delimited)'"
        )
        return None

    header = text.partition("\n")[0]
    if not header.strip():
        errors.append(f"{path.name}: berkas kosong atau tidak punya baris judul kolom")
        return None

    delimiter = ";" if header.count(";") > header.count(",") else ","
    # StringIO, bukan splitlines(): sel bertanda kutip boleh berisi ganti baris.
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    columns = tuple((c or "").strip() for c in (reader.fieldnames or []))

    rows: list[tuple[int, dict[str, str]]] = []
    for raw_row in reader:
        if None in raw_row:
            errors.append(f"{path.name}:{reader.line_num}: jumlah kolom lebih dari judul")
            continue
        row = {(k or "").strip(): (v or "").strip() for k, v in raw_row.items()}
        if not any(row.values()):
            continue
        rows.append((reader.line_num, row))
    return CsvTable(path.name, columns, tuple(rows), checksum)


def check_columns(
    name: str, columns: tuple[str, ...], expected: tuple[str, ...], errors: list[str]
) -> bool:
    """Kolom harus persis `expected` (urutan bebas). Kembalikan True bila cocok."""
    missing = [c for c in expected if c not in columns]
    unknown = [c for c in columns if c not in expected]
    duplicated = [c for c, n in Counter(columns).items() if n > 1]
    if missing:
        errors.append(f"{name}: kolom wajib tidak ada: {', '.join(missing)}")
    if unknown:
        errors.append(f"{name}: kolom tidak dikenal: {', '.join(unknown)}")
    if duplicated:
        errors.append(f"{name}: kolom ganda: {', '.join(duplicated)}")
    return not (missing or unknown or duplicated)
