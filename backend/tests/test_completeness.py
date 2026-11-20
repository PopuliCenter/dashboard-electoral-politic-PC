"""Laporan kelengkapan (T3.5), perhitungan murni tanpa database."""

import uuid

import pytest

from app.models.enums import DataStatus, ElectionType, RegionLevel
from app.reports.completeness import (
    ElectionInputs,
    RegionRef,
    VoteCoverage,
    summarize,
)
from app.reports.format import render_csv, render_text

PROV = RegionRef(uuid.uuid4(), "00", "Provinsi Uji", RegionLevel.PROVINCE)
KAB = RegionRef(uuid.uuid4(), "00.01", "Kabupaten Uji", RegionLevel.REGENCY)
KEC_1 = RegionRef(uuid.uuid4(), "00.01.01", "Kecamatan Uji Satu", RegionLevel.DISTRICT)
KEC_2 = RegionRef(uuid.uuid4(), "00.01.02", "Kecamatan Uji Dua", RegionLevel.DISTRICT)
KEC_3 = RegionRef(uuid.uuid4(), "00.01.03", "Kecamatan Uji Tiga", RegionLevel.DISTRICT)
OFF = DataStatus.OFFICIAL
UNOFF = DataStatus.UNOFFICIAL


def _dpr(**kwargs: object) -> ElectionInputs:
    base: dict[str, object] = {
        "election_type": ElectionType.LEGISLATIVE_DPR,
        "election_year": 2024,
        "regions": (PROV, KAB, KEC_1, KEC_2, KEC_3),
        "expected_items": frozenset({"UJI_A", "UJI_C"}),
        "votes": {
            KAB.id: frozenset({"UJI_A", "UJI_C"}),
            KEC_1.id: frozenset({"UJI_A", "UJI_C"}),
            KEC_2.id: frozenset({"UJI_A"}),
        },
        "statuses": {
            KAB.id: frozenset({OFF}),
            KEC_1.id: frozenset({OFF}),
            KEC_2.id: frozenset({OFF, UNOFF}),
        },
        "turnout": {KAB.id: frozenset({"valid_votes", "registered_voters"})},
    }
    base.update(kwargs)
    return ElectionInputs(**base)  # type: ignore[arg-type]


def test_ringkasan_per_tingkat_wilayah() -> None:
    report = summarize([_dpr()])
    by_level = {s.level: s for s in report.summaries}
    assert [s.level for s in report.summaries] == [
        RegionLevel.PROVINCE,
        RegionLevel.REGENCY,
        RegionLevel.DISTRICT,
    ]

    kec = by_level[RegionLevel.DISTRICT]
    assert kec.regions == 3
    assert kec.coverage == {
        VoteCoverage.COMPLETE: 1,
        VoteCoverage.PARTIAL: 1,
        VoteCoverage.EMPTY: 1,
    }
    assert kec.statuses == {OFF: 2, UNOFF: 1}
    assert kec.mixed_status == 1
    assert kec.percent(1) == pytest.approx(100 / 3)

    kab = by_level[RegionLevel.REGENCY]
    assert kab.coverage[VoteCoverage.COMPLETE] == 1
    assert kab.turnout == {"valid_votes": 1, "registered_voters": 1}

    prov = by_level[RegionLevel.PROVINCE]
    assert prov.coverage[VoteCoverage.EMPTY] == 1


def test_rincian_menyebut_partai_yang_kurang() -> None:
    details = {d.region.code: d for d in summarize([_dpr()]).details}
    assert details["00.01.02"].coverage is VoteCoverage.PARTIAL
    assert details["00.01.02"].missing_items == ("UJI_C",)
    assert details["00.01.03"].missing_items == ("UJI_A", "UJI_C")
    assert details["00.01.01"].missing_items == ()


def test_suara_partai_yang_tidak_ikut_pemilu_tidak_dihitung() -> None:
    """Baris untuk partai di luar daftar peserta tidak membuat wilayah lengkap."""
    report = summarize([_dpr(votes={KEC_1.id: frozenset({"UJI_A", "UJI_B"})})])
    detail = next(d for d in report.details if d.region == KEC_1)
    assert detail.coverage is VoteCoverage.PARTIAL
    assert detail.missing_items == ("UJI_C",)


def test_nomor_paslon_diurutkan_sebagai_angka() -> None:
    pilpres = _dpr(
        election_type=ElectionType.PRESIDENTIAL,
        expected_items=frozenset({"1", "2", "10"}),
        votes={},
        regions=(KEC_1,),
    )
    detail = summarize([pilpres]).details[0]
    assert detail.missing_items == ("1", "2", "10")


def test_kontestasi_dipisah_dalam_laporan() -> None:
    report = summarize([_dpr(), _dpr(election_type=ElectionType.LEGISLATIVE_DPRD_PROVINCE)])
    assert {(s.election_type, s.level) for s in report.summaries} >= {
        (ElectionType.LEGISLATIVE_DPR, RegionLevel.DISTRICT),
        (ElectionType.LEGISLATIVE_DPRD_PROVINCE, RegionLevel.DISTRICT),
    }
    assert len(report.summaries) == 6


def test_referensi_kosong_diberi_peringatan() -> None:
    report = summarize([_dpr(regions=(), expected_items=frozenset())])
    assert any("impor wilayah" in w for w in report.warnings)
    assert any("jalankan seed" in w for w in report.warnings)
    assert report.summaries == []


def test_teks_memuat_persentase_berkoma_dan_rincian() -> None:
    text = render_text(summarize([_dpr()]), database="produksi", detail=True)
    assert "legislative_dpr 2024" in text
    assert "kecamatan" in text
    assert "1 (33,3%)" in text
    assert "00.01.02 Kecamatan Uji Dua: kurang UJI_C" in text
    assert "00.01.03 Kecamatan Uji Tiga: kurang semua" in text


def test_csv_satu_baris_per_wilayah() -> None:
    lines = render_csv(summarize([_dpr()])).splitlines()
    assert lines[0].startswith("election_type,election_year,region_level,region_code")
    assert len(lines) == 1 + 5
    kec_2 = next(line for line in lines if ",00.01.02," in line)
    assert ",sebagian,UJI_C," in kec_2
    assert kec_2.endswith("official;unofficial")
    kab = next(line for line in lines if ",00.01," in line)
    assert ",ya,tidak,ya,tidak," in kab
