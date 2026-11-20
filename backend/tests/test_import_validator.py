"""Validator format impor baku (T3.1), tanpa database."""

from dataclasses import replace
from pathlib import Path

import pytest

from app.importer.format import RecordKind
from app.importer.validator import (
    CandidateVote,
    PartyVote,
    Turnout,
    ValidationReport,
    validate_file,
)
from app.models.enums import DataStatus, ElectionType
from tests.import_fixtures import (
    katalog_fiktif,
    partisipasi,
    suara_partai,
    suara_paslon,
    tulis_csv,
)


def _validasi(tmp_path: Path, rows: list[dict[str, str]], **kwargs: str) -> ValidationReport:
    return validate_file(tulis_csv(tmp_path / "impor.csv", rows, **kwargs), katalog_fiktif())


def _ada(report: ValidationReport, potongan: str) -> bool:
    return any(potongan in e for e in report.errors)


# --------------------------------------------------------------------------- #
# Berkas yang benar
# --------------------------------------------------------------------------- #


def test_suara_partai_yang_benar_lolos(tmp_path: Path) -> None:
    report = _validasi(
        tmp_path,
        [
            suara_partai("00.01.01", "UJI_A", "120"),
            suara_partai("00.01.01", "UJI_C", "0"),
            suara_partai("00.01", "UJI_A", "120"),
        ],
    )
    assert report.passed, report.errors
    assert report.kind is RecordKind.PARTY_VOTES
    assert report.election == (ElectionType.LEGISLATIVE_DPR, 2024)
    assert report.data_status is DataStatus.OFFICIAL
    assert report.records == [
        PartyVote(2, "00.01.01", "UJI_A", 120),
        PartyVote(3, "00.01.01", "UJI_C", 0),
        PartyVote(4, "00.01", "UJI_A", 120),
    ]
    assert len(report.checksum or "") == 64


def test_suara_paslon_yang_benar_lolos(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_paslon(pair="1"), suara_paslon(pair="3", votes="7")])
    assert report.passed, report.errors
    assert report.kind is RecordKind.CANDIDATE_VOTES
    assert report.records == [
        CandidateVote(2, "00.01.01", 1, 100),
        CandidateVote(3, "00.01.01", 3, 7),
    ]


def test_partisipasi_boleh_sebagian_tidak_tersedia(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [partisipasi(dpt="", tidak_sah="")])
    assert report.passed, report.errors
    assert report.kind is RecordKind.TURNOUT
    assert report.records == [Turnout(2, "00.01.01", None, 800, 780, None)]


def test_csv_excel_berlokal_indonesia_diterima(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai()], delimiter=";")
    assert report.passed, report.errors


# --------------------------------------------------------------------------- #
# Jenis berkas dan kolom
# --------------------------------------------------------------------------- #


def test_jenis_berkas_tidak_dikenali(tmp_path: Path) -> None:
    baris = suara_partai()
    del baris["party_code"]
    report = _validasi(tmp_path, [baris])
    assert _ada(report, "jenis berkas tidak dikenali")


def test_berkas_mencampur_jenis_data_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [{**suara_partai(), "pair_number": "1"}])
    assert _ada(report, "mencampur beberapa jenis data")


def test_kolom_kurang_dan_kolom_asing_dilaporkan(tmp_path: Path) -> None:
    baris = suara_partai()
    del baris["data_status"]
    baris["vote_share"] = "12.5"
    report = _validasi(tmp_path, [baris])
    assert _ada(report, "kolom wajib tidak ada: data_status")
    assert _ada(report, "kolom tidak dikenal: vote_share")


def test_berkas_tanpa_baris_data_ditolak(tmp_path: Path) -> None:
    path = tmp_path / "impor.csv"
    path.write_text(",".join(suara_partai()) + "\n", encoding="utf-8")
    report = validate_file(path, katalog_fiktif())
    assert _ada(report, "tidak ada baris data")


def test_berkas_hilang_dilaporkan(tmp_path: Path) -> None:
    report = validate_file(tmp_path / "tidak-ada.csv", katalog_fiktif())
    assert _ada(report, "berkas tidak ditemukan")


# --------------------------------------------------------------------------- #
# Kontestasi dan status
# --------------------------------------------------------------------------- #


def test_satu_berkas_hanya_satu_kontestasi(tmp_path: Path) -> None:
    report = _validasi(
        tmp_path,
        [
            suara_partai(tahun="2024"),
            suara_partai(tahun="2019", party="UJI_B"),
        ],
    )
    assert _ada(report, "hanya boleh satu kontestasi")
    assert report.records == []


def test_dpr_dan_dprd_tidak_boleh_dicampur(tmp_path: Path) -> None:
    report = _validasi(
        tmp_path,
        [suara_partai(jenis="legislative_dpr"), suara_partai(jenis="legislative_dprd_province")],
    )
    assert _ada(report, "hanya boleh satu kontestasi")


def test_satu_berkas_hanya_satu_data_status(tmp_path: Path) -> None:
    report = _validasi(
        tmp_path,
        [suara_partai("00.01.01"), suara_partai("00.01.03", status="unofficial")],
    )
    assert _ada(report, "hanya boleh satu data_status")


def test_jenis_kontestasi_tidak_dikenal(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(jenis="pilkada")])
    assert _ada(report, "election_type 'pilkada' tidak dikenal")


def test_kontestasi_tidak_ada_di_database(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(tahun="2014")])
    assert _ada(report, "kontestasi legislative_dpr 2014 tidak ada di database")


def test_data_status_tidak_dikenal(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(status="resmi")])
    assert _ada(report, "data_status 'resmi' tidak dikenal")


def test_data_tidak_resmi_lolos_dengan_peringatan(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(status="unofficial")])
    assert report.passed, report.errors
    assert any("keputusan terbuka" in w for w in report.warnings)


def test_suara_partai_untuk_pilpres_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(jenis="presidential")])
    assert _ada(report, "Pilpres 2024 tidak punya suara partai")


def test_suara_paslon_untuk_legislatif_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_paslon(jenis="legislative_dpr")])
    assert _ada(report, "suara pasangan calon hanya untuk Pilpres")


# --------------------------------------------------------------------------- #
# Wilayah
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kode", ["1.01", "00-01", "0001", "00.01.01.2001", "00.1"])
def test_format_kode_wilayah_salah_ditolak(tmp_path: Path, kode: str) -> None:
    report = _validasi(tmp_path, [suara_partai(region=kode)])
    assert _ada(report, "bukan format kode Kemendagri")


def test_kode_wilayah_tidak_dikenal_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(region="00.09.01")])
    assert _ada(report, "region_code 00.09.01 tidak dikenal")


def test_kode_wilayah_harus_berlaku_pada_tahun_pemilu(tmp_path: Path) -> None:
    # 00.01.02 hanya ada di 2019; 00.01.03 hanya ada di 2024.
    assert _validasi(tmp_path, [suara_partai("00.01.02", "UJI_B", tahun="2019")]).passed
    report = _validasi(tmp_path, [suara_partai("00.01.02", tahun="2024")])
    assert _ada(report, "tidak berlaku pada Pemilu 2024")
    report = _validasi(tmp_path, [suara_partai("00.01.03", "UJI_B", tahun="2019")])
    assert _ada(report, "tidak berlaku pada Pemilu 2019")


def test_kode_wilayah_kosong_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(region="")])
    assert _ada(report, "region_code wajib diisi")


# --------------------------------------------------------------------------- #
# Partai dan paslon
# --------------------------------------------------------------------------- #


def test_partai_tidak_dikenal_diringkas_sekali(tmp_path: Path) -> None:
    report = _validasi(
        tmp_path, [suara_partai(r, "UJI_Z") for r in ("00.01.01", "00.01.03", "00.01")]
    )
    pesan = [e for e in report.errors if "UJI_Z" in e]
    assert len(pesan) == 1
    assert "baris 2, 3, 4" in pesan[0]


def test_partai_yang_tidak_ikut_pemilu_itu_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(party="UJI_B", tahun="2024")])
    assert _ada(report, "partai UJI_B tidak ikut Pemilu 2024")
    report = _validasi(tmp_path, [suara_partai("00.01.02", "UJI_C", tahun="2019")])
    assert _ada(report, "partai UJI_C tidak ikut Pemilu 2019")


def test_paslon_yang_tidak_ada_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_paslon(pair="3", tahun="2019", region="00.01.02")])
    assert _ada(report, "pasangan calon nomor 3 tidak ada di Pilpres 2019")


@pytest.mark.parametrize("nomor", ["0", "", "satu", "-1"])
def test_nomor_paslon_harus_bilangan_positif(tmp_path: Path, nomor: str) -> None:
    report = _validasi(tmp_path, [suara_paslon(pair=nomor)])
    assert _ada(report, "pair_number")


# --------------------------------------------------------------------------- #
# Angka suara
# --------------------------------------------------------------------------- #


def test_suara_negatif_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(votes="-5")])
    assert _ada(report, "vote_count tidak boleh negatif")


def test_pemisah_ribuan_ditolak_dengan_petunjuk(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(votes="1.234.567")])
    assert _ada(report, "tulis tanpa pemisah ribuan, yaitu 1234567")


def test_angka_desimal_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(votes="120.5")])
    assert _ada(report, "harus bilangan bulat, bukan desimal")


def test_suara_kosong_ditolak_bukan_ditebak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(votes="")])
    assert _ada(report, "jangan diisi perkiraan")
    assert report.records == []


@pytest.mark.parametrize("nilai", ["abc", "12a", "1e3"])
def test_suara_bukan_angka_ditolak(tmp_path: Path, nilai: str) -> None:
    report = _validasi(tmp_path, [suara_partai(votes=nilai)])
    assert _ada(report, "bukan bilangan bulat")


def test_partisipasi_negatif_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [partisipasi(sah="-1")])
    assert _ada(report, "valid_votes tidak boleh negatif")


def test_partisipasi_kosong_semua_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [partisipasi(dpt="", hadir="", sah="", tidak_sah="")])
    assert _ada(report, "semua angka partisipasi kosong")


def test_partisipasi_yang_tidak_cocok_hanya_peringatan(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [partisipasi(dpt="700", hadir="800", sah="700", tidak_sah="20")])
    assert report.passed, report.errors
    assert any("tidak sama dengan pengguna hak pilih" in w for w in report.warnings)
    assert any("melebihi DPT" in w for w in report.warnings)


# --------------------------------------------------------------------------- #
# Duplikat dan pelaporan
# --------------------------------------------------------------------------- #


def test_baris_ganda_suara_partai_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(), suara_partai(votes="99")])
    assert _ada(report, "wilayah 00.01.01 dan UJI_A muncul lebih dari sekali (baris 2, 3)")


def test_baris_ganda_partisipasi_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [partisipasi(), partisipasi()])
    assert _ada(report, "wilayah 00.01.01 muncul lebih dari sekali")


def test_wilayah_sama_partai_berbeda_bukan_duplikat(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(party="UJI_A"), suara_partai(party="UJI_C")])
    assert report.passed, report.errors


def test_semua_kesalahan_baris_dilaporkan_sekaligus(tmp_path: Path) -> None:
    report = _validasi(
        tmp_path,
        [
            suara_partai(region="99.99.99"),
            suara_partai(votes="-1"),
            suara_partai(party="UJI_B"),
        ],
    )
    assert _ada(report, "impor.csv:2: region_code 99.99.99")
    assert _ada(report, "impor.csv:3: vote_count tidak boleh negatif")
    assert _ada(report, "partai UJI_B tidak ikut Pemilu 2024 (baris 4)")


def test_berkas_gagal_tidak_membawa_baris_apa_pun(tmp_path: Path) -> None:
    """Data yang gagal validasi tidak boleh separuh masuk (aturan data 6)."""
    report = _validasi(tmp_path, [suara_partai(), suara_partai(region="00.09.09")])
    assert not report.passed
    assert report.records == []


# --------------------------------------------------------------------------- #
# Temuan review T3.1
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nilai", ["120¹", "\u0661\u0662\u0660", "\uff11\uff12\uff10"])
def test_angka_bukan_ascii_ditolak_bukan_crash(tmp_path: Path, nilai: str) -> None:
    report = _validasi(tmp_path, [suara_partai(votes=nilai)])
    assert _ada(report, "karakter selain angka 0-9")


@pytest.mark.parametrize("nomor", ["²", "\u0661"])
def test_nomor_paslon_bukan_ascii_ditolak(tmp_path: Path, nomor: str) -> None:
    report = _validasi(tmp_path, [suara_paslon(pair=nomor)])
    assert _ada(report, "pair_number")


def test_tahun_dengan_catatan_kaki_ditolak(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(tahun="2024¹")])
    assert _ada(report, "harus tahun")


def test_suara_melebihi_bigint_ditolak_di_validator(tmp_path: Path) -> None:
    report = _validasi(tmp_path, [suara_partai(votes="9" * 25)])
    assert _ada(report, "terlalu besar")


def test_baris_partisipasi_terpotong_tidak_jadi_tidak_tersedia(tmp_path: Path) -> None:
    path = tmp_path / "impor.csv"
    path.write_text(
        "data_status,election_type,election_year,region_code,registered_voters,"
        "voters_turned_out,valid_votes,invalid_votes\n"
        "official,legislative_dpr,2024,00.01.01,1000,800\n",
        encoding="utf-8",
    )
    report = validate_file(path, katalog_fiktif())
    assert _ada(report, "jumlah kolom kurang dari judul")
    assert report.records == []


def test_internal_aggregate_ditolak_untuk_hasil_pemilu(tmp_path: Path) -> None:
    for baris in (
        suara_partai(status="internal_aggregate"),
        suara_paslon(status="internal_aggregate"),
        partisipasi(status="internal_aggregate"),
    ):
        report = _validasi(tmp_path, [baris])
        assert _ada(report, "internal_aggregate tidak berlaku untuk hasil pemilu")


def test_kode_wilayah_berversi_ganda_ditolak(tmp_path: Path) -> None:
    key = (ElectionType.LEGISLATIVE_DPR, 2024)
    catalog = replace(katalog_fiktif(), ambiguous_regions={key: frozenset({"00.01.01"})})
    report = validate_file(tulis_csv(tmp_path / "impor.csv", [suara_partai()]), catalog)
    assert _ada(report, "lebih dari satu versi")


def test_kontestasi_tanpa_tanggal_disebut_jelas(tmp_path: Path) -> None:
    key = (ElectionType.LEGISLATIVE_DPR, 2024)
    catalog = replace(katalog_fiktif(), undated_elections=frozenset({key}))
    report = validate_file(tulis_csv(tmp_path / "impor.csv", [suara_partai()]), catalog)
    assert _ada(report, "belum punya tanggal pemungutan suara")
    assert not _ada(report, "region_code")
