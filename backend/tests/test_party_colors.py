"""Warna partai dari konfigurasi (T4.5)."""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.party_colors import (
    FALLBACK_PALETTE,
    PartyColorError,
    load_party_colors,
)

PARTIES = "party_code,party_name\nUJI_A,Partai A\nUJI_B,Partai B\nUJI_C,Partai C\n"
HEADER = "party_code,color,source,verified_by\n"


def _folder(tmp_path: Path, colors: str) -> Path:
    (tmp_path / "parties.csv").write_text(PARTIES, encoding="utf-8")
    (tmp_path / "party_colors.csv").write_text(HEADER + colors, encoding="utf-8")
    return tmp_path


def test_warna_terkonfigurasi_dipakai(tmp_path: Path) -> None:
    config = load_party_colors(_folder(tmp_path, "UJI_A,#12ab34,https://uji.invalid/logo,AB\n"))
    warna = config.color_for("UJI_A")
    assert (warna.color, warna.source) == ("#12AB34", "config")


def test_warna_kosong_memakai_cadangan_yang_ditandai(tmp_path: Path) -> None:
    config = load_party_colors(_folder(tmp_path, "UJI_A,,,\n"))
    warna = config.color_for("UJI_A")
    assert warna.source == "fallback" and warna.color in FALLBACK_PALETTE


def test_cadangan_stabil_dan_berbeda_antarpartai(tmp_path: Path) -> None:
    config = load_party_colors(_folder(tmp_path, ""))
    warna = [config.color_for(code).color for code in ("UJI_A", "UJI_B", "UJI_C")]
    assert len(set(warna)) == 3
    assert warna == [config.color_for(code).color for code in ("UJI_A", "UJI_B", "UJI_C")]
    assert config.color_for("UJI_Z").color in FALLBACK_PALETTE  # di luar daftar


@pytest.mark.parametrize(
    ("baris", "pesan"),
    [
        ("UJI_A,merah,https://uji.invalid,AB\n", "#RRGGBB"),
        ("UJI_A,#12AB3,https://uji.invalid,AB\n", "#RRGGBB"),
        ("UJI_A,#12AB34,,AB\n", "wajib punya source"),
        ("UJI_X,#12AB34,https://uji.invalid,AB\n", "tidak ada di parties.csv"),
        ("UJI_A,,,\nUJI_A,,,\n", "sudah ada di baris"),
    ],
)
def test_konfigurasi_keliru_ditolak(tmp_path: Path, baris: str, pesan: str) -> None:
    with pytest.raises(PartyColorError, match=pesan):
        load_party_colors(_folder(tmp_path, baris))


def test_berkas_konfigurasi_sungguhan_sah() -> None:
    """data/reference/party_colors.csv di repo harus selalu bisa dibaca."""
    directory = Path(get_settings().reference_data_dir)
    if not (directory / "party_colors.csv").is_file():
        pytest.skip(f"data referensi tidak ter-mount di {directory}")
    config = load_party_colors(directory)
    # Setiap partai referensi punya warna (terkonfigurasi atau cadangan) yang
    # tidak sama dengan partai lain.
    warna = [config.color_for(code).color for code in config.order]
    assert len(config.order) == 20
    assert len(set(warna)) == len(warna)
