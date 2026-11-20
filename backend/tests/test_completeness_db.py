"""Laporan kelengkapan (T3.5) dari database sungguhan, dengan data fiktif di-rollback."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.staging import SourceInfo, load_into_staging
from app.importer.catalog import load_catalog
from app.importer.validator import validate_file
from app.models.enums import ElectionType, RegionLevel
from app.reports.completeness import VoteCoverage, load_inputs, summarize
from tests.import_fixtures import (
    isi_referensi_fiktif,
    partisipasi,
    suara_partai,
    suara_paslon,
    tulis_csv,
)

pytestmark = pytest.mark.integration

SUMBER = SourceInfo(source_name="Dokumen Uji T3.5", source_type="uji")


async def _muat(session: AsyncSession, path: Path, rows: list[dict[str, str]], name: str) -> None:
    report = validate_file(tulis_csv(path, rows), await load_catalog(session))
    assert report.passed, report.errors
    await load_into_staging(
        session, report, dataset_name=name, source=SUMBER, file_reference=path.name
    )


async def test_kelengkapan_dari_database(session: AsyncSession, tmp_path: Path) -> None:
    await isi_referensi_fiktif(session, tmp_path / "ref")
    # DPR 2024: kecamatan 00.01.02 lengkap (UJI_A dan UJI_C), kab/kota hanya UJI_A.
    await _muat(
        session,
        tmp_path / "dpr.csv",
        [
            suara_partai("00.01.02", "UJI_A", "10"),
            suara_partai("00.01.02", "UJI_C", "0"),
            suara_partai("00.01", "UJI_A", "10"),
        ],
        "uji-dpr-2024",
    )
    await _muat(session, tmp_path / "pilpres.csv", [suara_paslon("00.01.02", "1", "5")], "uji-p")
    await _muat(session, tmp_path / "t.csv", [partisipasi("00.01.02", dpt="")], "uji-t")

    inputs = await load_inputs(
        session,
        [(ElectionType.LEGISLATIVE_DPR, 2024), (ElectionType.PRESIDENTIAL, 2024)],
    )
    report = summarize(inputs)

    # Database pengembangan bisa berisi data referensi asli, jadi yang diperiksa
    # hanya wilayah dan partai fiktif.
    details = {
        (d.election_type, d.region.code): d
        for d in report.details
        if d.region.code.startswith("00")
    }
    dpr_kec = details[(ElectionType.LEGISLATIVE_DPR, "00.01.02")]
    assert "UJI_A" not in dpr_kec.missing_items and "UJI_C" not in dpr_kec.missing_items
    assert dpr_kec.turnout_fields == {"voters_turned_out", "valid_votes", "invalid_votes"}

    dpr_kab = details[(ElectionType.LEGISLATIVE_DPR, "00.01")]
    assert "UJI_C" in dpr_kab.missing_items and "UJI_A" not in dpr_kab.missing_items
    assert dpr_kab.coverage is not VoteCoverage.COMPLETE

    # 00.01.01 hanya berlaku di 2019, jadi tidak muncul di laporan 2024.
    assert (ElectionType.LEGISLATIVE_DPR, "00.01.01") not in details

    pilpres_kec = details[(ElectionType.PRESIDENTIAL, "00.01.02")]
    assert "1" not in pilpres_kec.missing_items and "2" in pilpres_kec.missing_items
    assert dpr_kec.region.level is RegionLevel.DISTRICT
