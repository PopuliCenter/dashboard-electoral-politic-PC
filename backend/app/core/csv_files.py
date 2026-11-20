"""Pembaca CSV bersama untuk berkas yang disunting manusia (seed T2.5, impor T3.1).

Menerima dua kebiasaan Excel: BOM UTF-8 di awal berkas, dan titik koma sebagai
pemisah kolom (bawaan Excel berlokal Indonesia, karena koma dipakai sebagai
pemisah desimal). Kesalahan tidak dilempar, tetapi ditambahkan ke daftar
`errors` supaya pemanggil bisa melaporkan semuanya sekaligus.
"""

import csv
import hashlib
import io
import re
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
    try:
        for raw_row in reader:
            if None in raw_row:
                errors.append(f"{path.name}:{reader.line_num}: jumlah kolom lebih dari judul")
                continue
            row = {(k or "").strip(): (v or "").strip() for k, v in raw_row.items()}
            if not any(row.values()):
                continue
            # DictReader mengisi kolom yang hilang dengan None. Baris terpotong
            # tidak boleh terbaca sebagai "angka tidak tersedia".
            if any(v is None for v in raw_row.values()):
                errors.append(f"{path.name}:{reader.line_num}: jumlah kolom kurang dari judul")
                continue
            rows.append((reader.line_num, row))
    except csv.Error as exc:
        # Biasanya tanda kutip yang tidak ditutup: sisa berkas terbaca sebagai
        # satu sel raksasa sampai batas panjang sel. Batasnya sengaja tidak
        # dinaikkan, karena batas itulah yang menangkap kesalahan ini.
        errors.append(
            f"{path.name}: berkas rusak setelah baris {reader.line_num} ({exc}); "
            "periksa tanda kutip yang tidak ditutup"
        )
        return None
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


# Batas kolom PostgreSQL. Angka di atasnya ditolak di sini dengan pesan jelas,
# bukan oleh database saat pemuatan.
INTEGER_MAX = 2**31 - 1
BIGINT_MAX = 2**63 - 1

_ASCII_DIGITS = re.compile(r"[0-9]+")
_THOUSANDS = re.compile(r"[0-9]{1,3}([.,][0-9]{3})+")
_DECIMAL = re.compile(r"[0-9]+[.,][0-9]+")


def parse_whole_number(value: str, *, maximum: int = INTEGER_MAX) -> int | str:
    """Bilangan bulat >= 0 dari teks sel. Kembalikan angka, atau pesan galat.

    Hanya digit ASCII 0-9. `str.isdigit()` tidak dipakai: ia menerima superskrip
    (catatan kaki "120¹" dari PDF) yang lalu membuat `int()` gagal, dan digit
    aksara lain (Arab-Indic, fullwidth) yang `int()` terima diam-diam.
    """
    if _ASCII_DIGITS.fullmatch(value):
        number = int(value)
        if number > maximum:
            return f"{value} terlalu besar (maksimum {maximum})"
        return number
    if value.startswith("-") and _ASCII_DIGITS.fullmatch(value[1:]):
        return f"tidak boleh negatif ({value})"
    if _THOUSANDS.fullmatch(value):
        return f"{value!r}: tulis tanpa pemisah ribuan, yaitu {re.sub(r'[.,]', '', value)}"
    if _DECIMAL.fullmatch(value):
        return f"{value!r} harus bilangan bulat, bukan desimal"
    if any(c.isdigit() and not ("0" <= c <= "9") for c in value):
        return (
            f"{value!r} berisi karakter selain angka 0-9 (misalnya tanda catatan kaki "
            "dari PDF, atau digit aksara lain); ketik ulang angkanya"
        )
    return f"{value!r} bukan bilangan bulat"
