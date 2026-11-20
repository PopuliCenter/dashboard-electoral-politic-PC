"""Warna partai dari konfigurasi (T4.5), bukan hard-code.

Sumbernya `data/reference/party_colors.csv`:

    party_code,color,source,verified_by
    PKB,#RRGGBB,<dokumen identitas visual resmi>,<inisial pemeriksa>

SDD bagian 14: warna harus mengikuti identitas visual partai dan tidak boleh
ditetapkan berdasarkan asumsi. Karena itu kolom `color` boleh kosong.

Partai tanpa warna resmi memakai cadangan NETRAL (gradasi abu-abu, keputusan
pengguna) bertanda `fallback`. Abu-abu tidak cukup untuk membedakan 18 partai,
jadi pembeda utamanya adalah NOMOR URUT partai pada tahun kontestasi itu, yang
wajib ditampilkan frontend di legenda dan label wilayah bila `color_source`
bernilai `fallback`. Rona khas partai (merah, kuning, hijau, biru, oranye) sengaja
tidak dipakai supaya peta tidak terbaca sebagai partai lain.

Perubahan berkas berlaku setelah layanan api di-restart (konfigurasi dibaca
sekali per proses).
"""

import hashlib
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.core.config import get_settings
from app.core.csv_files import check_columns, read_csv

logger = logging.getLogger(__name__)

COLORS_FILE = "party_colors.csv"
PARTIES_FILE = "parties.csv"
COLUMNS = ("party_code", "color", "source", "verified_by")

# Gradasi abu-abu netral, dari gelap ke terang. Bukan warna partai mana pun.
FALLBACK_PALETTE: tuple[str, ...] = (
    "#3F3F46",
    "#71717A",
    "#A1A1AA",
    "#52525B",
    "#D4D4D8",
    "#27272A",
    "#8E8E96",
    "#BDBDC4",
)


def _is_hex_color(value: str) -> bool:
    return (
        len(value) == 7
        and value[0] == "#"
        and all(c in "0123456789abcdefABCDEF" for c in value[1:])
    )


class PartyColorError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class PartyColor:
    color: str
    source: Literal["config", "fallback"]


@dataclass(frozen=True)
class PartyColorConfig:
    # party_code -> warna terkonfigurasi yang sah (hanya yang terisi).
    configured: Mapping[str, str]
    # Urutan kode partai untuk palet cadangan: urutan baris di parties.csv,
    # supaya warna cadangan stabil.
    order: Sequence[str]
    # Masalah per baris; baris yang bermasalah diabaikan, sisanya tetap dipakai.
    errors: Sequence[str] = field(default_factory=tuple)

    def color_for(self, party_code: str) -> PartyColor:
        if party_code in self.configured:
            return PartyColor(self.configured[party_code], "config")
        if party_code in self.order:
            index = list(self.order).index(party_code)
        else:
            # Partai di luar daftar referensi (misalnya data uji): tetap stabil.
            index = int(hashlib.sha256(party_code.encode()).hexdigest(), 16)
        return PartyColor(FALLBACK_PALETTE[index % len(FALLBACK_PALETTE)], "fallback")


def parse_party_colors(directory: Path, *, require_verified: bool = False) -> PartyColorConfig:
    """Baca konfigurasi warna. Tidak melempar: masalah dikumpulkan di `errors`.

    Baris yang keliru diabaikan; urutan parties.csv dan baris lain yang sah tetap
    dipakai, supaya satu salah ketik tidak mengubah warna semua partai.
    `require_verified` (produksi): warna tanpa `verified_by` tidak dipakai.
    """
    errors: list[str] = []
    parties = read_csv(directory / PARTIES_FILE, errors)
    order = [row["party_code"] for _, row in parties.rows] if parties else []

    table = read_csv(directory / COLORS_FILE, errors)
    configured: dict[str, str] = {}
    if table is None or not check_columns(table.name, table.columns, COLUMNS, errors):
        return PartyColorConfig({}, order, tuple(errors))

    seen_code: dict[str, int] = {}
    seen_color: dict[str, tuple[int, str]] = {}
    fallback = {c.upper() for c in FALLBACK_PALETTE}
    for line, row in table.rows:
        code = row["party_code"]
        where = f"{COLORS_FILE}:{line}"
        if code in seen_code:
            errors.append(f"{where}: party_code {code} sudah ada di baris {seen_code[code]}")
            continue
        seen_code[code] = line
        if order and code not in order:
            errors.append(f"{where}: party_code {code!r} tidak ada di {PARTIES_FILE}")
            continue
        color = row["color"].upper()
        if not color:
            continue
        if not _is_hex_color(color):
            errors.append(f"{where}: color {row['color']!r} harus berformat #RRGGBB")
        elif not row["source"]:
            errors.append(f"{where}: warna {code} wajib punya source (identitas visual resmi)")
        elif color in fallback:
            errors.append(
                f"{where}: warna {code} {color} sama dengan abu-abu cadangan; "
                "warna resmi tidak boleh tertukar dengan cadangan"
            )
        elif color in seen_color:
            other_line, other_code = seen_color[color]
            errors.append(
                f"{where}: warna {code} {color} sama dengan {other_code} (baris {other_line}); "
                "partai harus bisa dibedakan"
            )
        elif require_verified and not row["verified_by"]:
            errors.append(f"{where}: warna {code} belum diverifikasi (verified_by kosong)")
        else:
            seen_color[color] = (line, code)
            configured[code] = color
    return PartyColorConfig(configured, order, tuple(errors))


def load_party_colors(directory: Path, *, require_verified: bool = False) -> PartyColorConfig:
    """Seperti parse_party_colors, tetapi melempar PartyColorError bila ada masalah."""
    config = parse_party_colors(directory, require_verified=require_verified)
    if config.errors:
        raise PartyColorError(list(config.errors))
    return config


@lru_cache
def get_party_colors() -> PartyColorConfig:
    """Konfigurasi untuk API, dibaca sekali per proses.

    Masalah per baris dicatat di log dan baris itu memakai cadangan; berkas
    yang keliru tidak mematikan API. Di produksi, warna yang belum
    diverifikasi tidak dipakai.
    """
    settings = get_settings()
    config = parse_party_colors(
        Path(settings.reference_data_dir),
        require_verified=settings.app_env == "production",
    )
    for error in config.errors:
        logger.error("konfigurasi warna partai: %s", error)
    return config
