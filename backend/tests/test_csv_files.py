"""Pembaca CSV dan parser angka bersama (dipakai seed T2.5 dan impor T3.1)."""

from pathlib import Path

import pytest

from app.core.csv_files import BIGINT_MAX, INTEGER_MAX, parse_whole_number, read_csv


@pytest.mark.parametrize(("teks", "angka"), [("0", 0), ("120", 120), ("007", 7)])
def test_angka_ascii_diterima(teks: str, angka: int) -> None:
    assert parse_whole_number(teks) == angka


@pytest.mark.parametrize(
    ("teks", "pesan"),
    [
        ("120¹", "karakter selain angka 0-9"),  # catatan kaki dari PDF
        ("²", "karakter selain angka 0-9"),
        ("\u0661\u0662\u0660", "karakter selain angka 0-9"),  # digit Arab-Indic
        ("\uff11\uff12\uff10", "karakter selain angka 0-9"),  # digit fullwidth
        ("-5", "tidak boleh negatif"),
        ("1.234.567", "tanpa pemisah ribuan, yaitu 1234567"),
        ("12,5", "bukan desimal"),
        ("abc", "bukan bilangan bulat"),
        (" 12", "bukan bilangan bulat"),
        ("12a", "bukan bilangan bulat"),
    ],
)
def test_angka_yang_tidak_sah_ditolak_dengan_pesan(teks: str, pesan: str) -> None:
    hasil = parse_whole_number(teks)
    assert isinstance(hasil, str) and pesan in hasil


def test_batas_atas_kolom_database() -> None:
    assert parse_whole_number(str(INTEGER_MAX)) == INTEGER_MAX
    assert "terlalu besar" in str(parse_whole_number(str(INTEGER_MAX + 1)))
    assert parse_whole_number(str(BIGINT_MAX), maximum=BIGINT_MAX) == BIGINT_MAX
    assert "terlalu besar" in str(parse_whole_number("9" * 25, maximum=BIGINT_MAX))


def test_baris_kekurangan_kolom_ditolak(tmp_path: Path) -> None:
    path = tmp_path / "a.csv"
    path.write_text("a,b,c\n1,2,3\n4,5\n", encoding="utf-8")
    errors: list[str] = []
    table = read_csv(path, errors)
    assert errors == ["a.csv:3: jumlah kolom kurang dari judul"]
    assert table is not None and [line for line, _ in table.rows] == [2]


def test_baris_pendek_yang_kosong_tetap_dilewati(tmp_path: Path) -> None:
    path = tmp_path / "a.csv"
    path.write_text("a,b,c\n1,2,3\n,\n", encoding="utf-8")
    errors: list[str] = []
    assert read_csv(path, errors) is not None
    assert errors == []


def test_kutip_tidak_ditutup_dilaporkan_bukan_crash(tmp_path: Path) -> None:
    path = tmp_path / "a.csv"
    isi = 'a,b\n1,2\n3,"tidak ditutup\n' + ("x,y\n" * 40_000)
    path.write_text(isi, encoding="utf-8")
    errors: list[str] = []
    assert read_csv(path, errors) is None
    assert len(errors) == 1 and "tanda kutip yang tidak ditutup" in errors[0]
