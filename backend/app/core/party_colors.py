"""Warna partai dari konfigurasi (T4.5), bukan hard-code.

Sumbernya `data/reference/party_colors.csv`:

    party_code,color,source,verified_by
    PKB,#RRGGBB,<dokumen identitas visual resmi>,<inisial pemeriksa>

SDD bagian 14: warna harus mengikuti identitas visual partai dan tidak boleh
ditetapkan berdasarkan asumsi. Karena itu kolom `color` boleh kosong. Partai
tanpa warna terkonfigurasi memakai palet cadangan kontras tinggi yang ditandai
`fallback`, supaya peta tetap terbaca tanpa mengaku sebagai identitas partai.
"""

import hashlib
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.core.config import get_settings
from app.core.csv_files import check_columns, read_csv

logger = logging.getLogger(__name__)

COLORS_FILE = "party_colors.csv"
PARTIES_FILE = "parties.csv"
COLUMNS = ("party_code", "color", "source", "verified_by")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

# 20 warna kontras tinggi dari daftar Kelly (1965), tanpa putih dan hitam. Ini
# bukan warna partai mana pun; hanya pembeda sementara.
FALLBACK_PALETTE: tuple[str, ...] = (
    "#F3C300",
    "#875692",
    "#F38400",
    "#A1CAF1",
    "#BE0032",
    "#C2B280",
    "#848482",
    "#008856",
    "#E68FAC",
    "#0067A5",
    "#F99379",
    "#604E97",
    "#F6A600",
    "#B3446C",
    "#DCD300",
    "#882D17",
    "#8DB600",
    "#654522",
    "#E25822",
    "#2B3D26",
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
    # party_code -> warna terkonfigurasi (hanya yang terisi).
    configured: Mapping[str, str]
    # Urutan kode partai untuk palet cadangan: urutan baris di parties.csv,
    # supaya warna cadangan stabil dan tidak bertabrakan antarpartai.
    order: Sequence[str]

    def color_for(self, party_code: str) -> PartyColor:
        if party_code in self.configured:
            return PartyColor(self.configured[party_code].upper(), "config")
        if party_code in self.order:
            index = list(self.order).index(party_code)
        else:
            # Partai di luar daftar referensi (misalnya data uji): tetap stabil.
            index = int(hashlib.sha256(party_code.encode()).hexdigest(), 16)
        return PartyColor(FALLBACK_PALETTE[index % len(FALLBACK_PALETTE)], "fallback")


def load_party_colors(directory: Path) -> PartyColorConfig:
    """Baca dan validasi konfigurasi warna. Melempar PartyColorError bila keliru."""
    errors: list[str] = []
    parties = read_csv(directory / PARTIES_FILE, errors)
    order = [row["party_code"] for _, row in parties.rows] if parties else []

    table = read_csv(directory / COLORS_FILE, errors)
    configured: dict[str, str] = {}
    if table is not None and check_columns(table.name, table.columns, COLUMNS, errors):
        seen: dict[str, int] = {}
        for line, row in table.rows:
            code = row["party_code"]
            where = f"{COLORS_FILE}:{line}"
            if code in seen:
                errors.append(f"{where}: party_code {code} sudah ada di baris {seen[code]}")
                continue
            seen[code] = line
            if order and code not in order:
                errors.append(f"{where}: party_code {code!r} tidak ada di {PARTIES_FILE}")
            color = row["color"]
            if not color:
                continue
            if not HEX_COLOR.match(color):
                errors.append(f"{where}: color {color!r} harus berformat #RRGGBB")
            elif not row["source"]:
                errors.append(f"{where}: warna {code} wajib punya source (identitas visual resmi)")
            else:
                configured[code] = color
    if errors:
        raise PartyColorError(errors)
    return PartyColorConfig(configured, order)


@lru_cache
def get_party_colors() -> PartyColorConfig:
    """Konfigurasi untuk API. Bila berkas keliru, semua partai memakai cadangan
    dan galatnya dicatat: warna yang salah tidak sepadan dengan API yang mati."""
    directory = Path(get_settings().reference_data_dir)
    try:
        return load_party_colors(directory)
    except PartyColorError as exc:
        logger.error("konfigurasi warna partai tidak sah, memakai warna cadangan: %s", exc)
        return PartyColorConfig({}, [])
