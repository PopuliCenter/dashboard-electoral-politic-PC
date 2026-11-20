"""Validasi berkas data referensi (T2.5). Murni, tanpa database."""

from datetime import date
from pathlib import Path

import pytest

from app.models.enums import ElectionType
from app.seed.reference import (
    PARTY_COLUMNS,
    ReferenceDataError,
    check_verification,
    load_reference_data,
)
from tests.reference_fixtures import (
    kontestasi_fiktif,
    partai,
    partai_fiktif,
    paslon_fiktif,
    tulis_referensi,
)


def _galat(folder: Path) -> list[str]:
    with pytest.raises(ReferenceDataError) as info:
        load_reference_data(folder)
    return info.value.errors


def _ada(errors: list[str], *potongan: str) -> bool:
    return any(all(p in e for p in potongan) for e in errors)


# --------------------------------------------------------------------------- #
# Jalur bahagia
# --------------------------------------------------------------------------- #


def test_data_fiktif_lengkap_lolos(tmp_path: Path) -> None:
    data = load_reference_data(tulis_referensi(tmp_path))
    assert len(data.parties) == 3
    assert len(data.elections) == 6
    assert len(data.candidate_pairs) == 4
    assert set(data.checksums) == {"parties.csv", "elections.csv", "candidate_pairs.csv"}
    assert all(len(digest) == 64 for digest in data.checksums.values())


def test_keikutsertaan_diturunkan_dari_nomor_urut(tmp_path: Path) -> None:
    """Nomor urut adalah satu-satunya sumber kebenaran untuk contested_<tahun>."""
    data = load_reference_data(tulis_referensi(tmp_path))
    by_code = {p.party_code: p for p in data.parties}
    assert by_code["UJI_A"].contested(2019) and by_code["UJI_A"].contested(2024)
    assert by_code["UJI_B"].contested(2019) and not by_code["UJI_B"].contested(2024)
    assert not by_code["UJI_C"].contested(2019) and by_code["UJI_C"].contested(2024)


def test_nomor_urut_sama_di_tahun_berbeda_boleh(tmp_path: Path) -> None:
    """UJI_A memakai 901 di 2019 dan 2024; keduanya tidak berhubungan."""
    data = load_reference_data(tulis_referensi(tmp_path))
    a = next(p for p in data.parties if p.party_code == "UJI_A")
    assert a.ballot_numbers == {2019: 901, 2024: 901}


def test_kontestasi_dibaca_sebagai_enum_dan_tanggal(tmp_path: Path) -> None:
    data = load_reference_data(tulis_referensi(tmp_path))
    pilpres_2024 = next(
        e
        for e in data.elections
        if e.election_type is ElectionType.PRESIDENTIAL and e.election_year == 2024
    )
    assert pilpres_2024.election_date == date(2024, 1, 1)


def test_csv_excel_berlokal_indonesia_diterima(tmp_path: Path) -> None:
    """Excel id-ID menyimpan dengan BOM dan titik koma sebagai pemisah kolom."""
    biasa = load_reference_data(tulis_referensi(tmp_path / "biasa"))
    excel = load_reference_data(tulis_referensi(tmp_path / "excel", delimiter=";", bom=True))
    assert [p.party_code for p in excel.parties] == [p.party_code for p in biasa.parties]
    assert excel.elections == biasa.elections


def test_baris_kosong_di_akhir_dari_excel_diabaikan(tmp_path: Path) -> None:
    folder = tulis_referensi(tmp_path)
    berkas = folder / "parties.csv"
    berkas.write_bytes(berkas.read_bytes() + b",,,,,,,,\n,,,,,,,,\n")
    assert len(load_reference_data(folder).parties) == 3


def test_sel_bertanda_kutip_boleh_berisi_ganti_baris(tmp_path: Path) -> None:
    baris = partai_fiktif()
    baris[0]["notes"] = "baris pertama\nbaris kedua"
    data = load_reference_data(tulis_referensi(tmp_path, parties=baris))
    assert data.parties[0].notes == "baris pertama\nbaris kedua"


# --------------------------------------------------------------------------- #
# Format berkas
# --------------------------------------------------------------------------- #


def test_berkas_bukan_utf8_ditolak_dengan_petunjuk_excel(tmp_path: Path) -> None:
    """Excel 'CSV (Comma delimited)' menyimpan sebagai cp1252: tanda kutip lengkung jadi 0x92."""
    folder = tulis_referensi(tmp_path)
    teks = (folder / "parties.csv").read_text(encoding="utf-8")
    (folder / "parties.csv").write_bytes(
        teks.replace("Partai A", "Partai A" + chr(0x2019)).encode("cp1252")
    )
    assert _ada(_galat(folder), "parties.csv", "CSV UTF-8")


def test_berkas_hilang_dilaporkan(tmp_path: Path) -> None:
    folder = tulis_referensi(tmp_path)
    (folder / "elections.csv").unlink()
    assert _ada(_galat(folder), "elections.csv", "tidak ditemukan")


def test_kolom_wajib_hilang_ditolak(tmp_path: Path) -> None:
    kolom = tuple(c for c in PARTY_COLUMNS if c != "source_2024")
    assert _ada(_galat(tulis_referensi(tmp_path, party_columns=kolom)), "source_2024")


def test_kolom_tidak_dikenal_ditolak(tmp_path: Path) -> None:
    """Salah ketik nama kolom tidak boleh lolos diam-diam."""
    kolom = (*PARTY_COLUMNS, "ballot_nomber_2019")
    assert _ada(_galat(tulis_referensi(tmp_path, party_columns=kolom)), "ballot_nomber_2019")


# --------------------------------------------------------------------------- #
# Partai
# --------------------------------------------------------------------------- #


def test_kode_partai_ganda_ditolak_dengan_nomor_baris(tmp_path: Path) -> None:
    baris = [*partai_fiktif(), partai("UJI_A", "Partai A Kedua", nomor_2024=904)]
    errors = _galat(tulis_referensi(tmp_path, parties=baris))
    assert _ada(errors, "party_code", "UJI_A", "baris 2, 5")


def test_nama_partai_ganda_ditolak_tanpa_peduli_huruf_besar(tmp_path: Path) -> None:
    baris = [*partai_fiktif(), partai("UJI_D", "PARTAI A", nomor_2024=904)]
    assert _ada(_galat(tulis_referensi(tmp_path, parties=baris)), "party_name")


def test_nomor_urut_ganda_dalam_satu_tahun_ditolak(tmp_path: Path) -> None:
    baris = [*partai_fiktif(), partai("UJI_D", "Partai D", nomor_2019=901)]
    assert _ada(_galat(tulis_referensi(tmp_path, parties=baris)), "ballot_number_2019", "901")


@pytest.mark.parametrize("nilai", ["0", "-1", "abc", "1.5"])
def test_nomor_urut_harus_bilangan_bulat_positif(tmp_path: Path, nilai: str) -> None:
    baris = [partai("UJI_A", "Partai A", nomor_2019=nilai, nomor_2024=901)]
    assert _ada(_galat(tulis_referensi(tmp_path, parties=baris)), "ballot_number_2019")


def test_ikut_pemilu_tanpa_sumber_ditolak(tmp_path: Path) -> None:
    """Aturan data 5: tidak ada angka tanpa sumber."""
    baris = partai_fiktif()
    baris[0]["source_2024"] = ""
    assert _ada(_galat(tulis_referensi(tmp_path, parties=baris)), "source_2024 kosong")


def test_sumber_tanpa_nomor_urut_ditolak(tmp_path: Path) -> None:
    baris = partai_fiktif()
    baris[1]["source_2024"] = "https://kpu-uji.invalid/x"
    assert _ada(_galat(tulis_referensi(tmp_path, parties=baris)), "source_2024 terisi")


def test_partai_tanpa_nomor_urut_sama_sekali_ditolak(tmp_path: Path) -> None:
    baris = [*partai_fiktif(), partai("UJI_D", "Partai D")]
    assert _ada(_galat(tulis_referensi(tmp_path, parties=baris)), "minimal di satu pemilu")


def test_kode_partai_harus_huruf_kapital(tmp_path: Path) -> None:
    baris = [partai("uji-a", "Partai A", nomor_2019=901, nomor_2024=901)]
    assert _ada(_galat(tulis_referensi(tmp_path, parties=baris)), "party_code", "uji-a")


def test_teks_melebihi_panjang_kolom_database_ditolak(tmp_path: Path) -> None:
    baris = [partai("UJI_A", "P" * 151, nomor_2019=901, nomor_2024=901)]
    assert _ada(_galat(tulis_referensi(tmp_path, parties=baris)), "party_name", "150")


# --------------------------------------------------------------------------- #
# Kontestasi dan paslon
# --------------------------------------------------------------------------- #


def test_kontestasi_kurang_dari_enam_ditolak(tmp_path: Path) -> None:
    baris = kontestasi_fiktif()[:-1]
    errors = _galat(tulis_referensi(tmp_path, elections=baris))
    assert _ada(errors, "legislative_dprd_province 2024", "tepat 6")


def test_kontestasi_ganda_ditolak(tmp_path: Path) -> None:
    baris = kontestasi_fiktif()
    baris.append(dict(baris[0]))
    assert _ada(_galat(tulis_referensi(tmp_path, elections=baris)), "muncul lebih dari sekali")


def test_jenis_kontestasi_di_luar_fase_1_ditolak(tmp_path: Path) -> None:
    """DPRD kabupaten/kota dan Pilkada belum dibangun (CLAUDE.md)."""
    baris = kontestasi_fiktif()
    baris[2]["election_type"] = "legislative_dprd_regency"
    assert _ada(_galat(tulis_referensi(tmp_path, elections=baris)), "legislative_dprd_regency")


def test_tahun_di_luar_fase_1_ditolak(tmp_path: Path) -> None:
    baris = kontestasi_fiktif()
    baris[0]["election_year"] = "2014"
    baris[0]["election_date"] = "2014-04-09"
    assert _ada(_galat(tulis_referensi(tmp_path, elections=baris)), "2014", "di luar cakupan")


def test_tanggal_harus_di_tahun_yang_sama(tmp_path: Path) -> None:
    baris = kontestasi_fiktif()
    baris[0]["election_date"] = "2020-01-01"
    assert _ada(_galat(tulis_referensi(tmp_path, elections=baris)), "tidak berada di tahun 2019")


def test_tanggal_harus_iso(tmp_path: Path) -> None:
    baris = kontestasi_fiktif()
    baris[0]["election_date"] = "17/04/2019"
    assert _ada(_galat(tulis_referensi(tmp_path, elections=baris)), "YYYY-MM-DD")


def test_kontestasi_satu_tahun_harus_serentak(tmp_path: Path) -> None:
    baris = kontestasi_fiktif()
    baris[1]["election_date"] = "2019-01-02"
    assert _ada(_galat(tulis_referensi(tmp_path, elections=baris)), "serentak")


def test_nomor_paslon_harus_berurutan_dari_satu(tmp_path: Path) -> None:
    baris = paslon_fiktif()
    baris[1]["pair_number"] = "3"
    assert _ada(_galat(tulis_referensi(tmp_path, pairs=baris)), "berurutan", "2019")


def test_pilpres_tanpa_paslon_ditolak(tmp_path: Path) -> None:
    baris = [p for p in paslon_fiktif() if p["election_year"] == "2019"]
    assert _ada(_galat(tulis_referensi(tmp_path, pairs=baris)), "Pilpres 2024")


def test_paslon_ganda_ditolak(tmp_path: Path) -> None:
    baris = paslon_fiktif()
    baris.append(dict(baris[0]))
    assert _ada(_galat(tulis_referensi(tmp_path, pairs=baris)), "muncul lebih dari sekali")


# --------------------------------------------------------------------------- #
# Pelaporan dan gerbang verifikasi
# --------------------------------------------------------------------------- #


def test_semua_kesalahan_dilaporkan_sekaligus(tmp_path: Path) -> None:
    """Peneliti melihat semua masalah dalam satu kali jalan."""
    parties = [
        partai("UJI_A", "Partai A", nomor_2019="x", nomor_2024=901),
        partai("uji_b", "Partai B", nomor_2019=902),
    ]
    elections = kontestasi_fiktif()
    elections[0]["election_type"] = "pilkada"
    errors = _galat(tulis_referensi(tmp_path, parties=parties, elections=elections))
    assert _ada(errors, "ballot_number_2019")
    assert _ada(errors, "uji_b")
    assert _ada(errors, "pilkada")


def test_produksi_menolak_baris_yang_belum_diverifikasi(tmp_path: Path) -> None:
    data = load_reference_data(tulis_referensi(tmp_path))
    with pytest.raises(ReferenceDataError) as info:
        check_verification(data, "production")
    assert _ada(info.value.errors, "belum diverifikasi", "parties.csv:2")


def test_pengembangan_hanya_memperingatkan(tmp_path: Path) -> None:
    data = load_reference_data(tulis_referensi(tmp_path))
    peringatan = check_verification(data, "development")
    assert len(peringatan) == 1
    assert "13 baris belum diverifikasi" in peringatan[0]


def test_produksi_menerima_data_yang_sudah_diverifikasi_semua(tmp_path: Path) -> None:
    parties = [{**p, "verified_by": "peneliti-uji"} for p in partai_fiktif()]
    folder = tulis_referensi(
        tmp_path,
        parties=parties,
        elections=kontestasi_fiktif(verified_by="peneliti-uji"),
        pairs=paslon_fiktif(verified_by="peneliti-uji"),
    )
    assert check_verification(load_reference_data(folder), "production") == []


# --------------------------------------------------------------------------- #
# Temuan review T3.1 (pembaca CSV dan parser angka dipakai bersama)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nilai", ["9¹", "\u0661", "\uff19"])
def test_nomor_urut_bukan_ascii_ditolak_bukan_crash(tmp_path: Path, nilai: str) -> None:
    baris = [partai("UJI_A", "Partai A", nomor_2019=nilai, nomor_2024=901)]
    assert _ada(_galat(tulis_referensi(tmp_path, parties=baris)), "ballot_number_2019", "0-9")


def test_baris_partai_terpotong_ditolak(tmp_path: Path) -> None:
    folder = tulis_referensi(tmp_path)
    path = folder / "parties.csv"
    path.write_text(path.read_text(encoding="utf-8") + "UJI_D,Partai D\n", encoding="utf-8")
    assert _ada(_galat(folder), "parties.csv:", "jumlah kolom kurang dari judul")
