"""Katalog referensi validator impor dimuat dari database sungguhan (T3.1).

Data fiktif ditulis di transaksi yang di-rollback (aturan data 2). Database
pengembangan mungkin sudah berisi data referensi asli, jadi test memeriksa
keanggotaan, bukan isi katalog secara utuh.
"""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.importer.catalog import load_catalog
from app.importer.validator import validate_file
from app.models import Region
from app.models.enums import ElectionType, RegionLevel
from app.seed.apply import apply_reference_data
from app.seed.reference import load_reference_data
from tests.import_fixtures import suara_partai, suara_paslon, tulis_csv
from tests.reference_fixtures import tulis_referensi

pytestmark = pytest.mark.integration

DPR_2019 = (ElectionType.LEGISLATIVE_DPR, 2019)
DPR_2024 = (ElectionType.LEGISLATIVE_DPR, 2024)


async def _isi_referensi(session: AsyncSession, folder: Path) -> None:
    # Kontestasi fiktif bertanggal 2019-01-01 dan 2024-01-01.
    await apply_reference_data(session, load_reference_data(tulis_referensi(folder)))

    provinsi = Region(
        region_code="00",
        region_name="Provinsi Uji",
        region_level=RegionLevel.PROVINCE,
        valid_from=date(2000, 1, 1),
    )
    session.add(provinsi)
    await session.flush()
    kabupaten = Region(
        region_code="00.01",
        region_name="Kabupaten Uji",
        region_level=RegionLevel.REGENCY,
        parent_id=provinsi.id,
        valid_from=date(2000, 1, 1),
    )
    session.add(kabupaten)
    await session.flush()
    session.add_all(
        [
            Region(
                region_code="00.01.01",
                region_name="Kecamatan Uji Lama",
                region_level=RegionLevel.DISTRICT,
                parent_id=kabupaten.id,
                valid_from=date(2000, 1, 1),
                # Inklusif: masih berlaku pada hari pemungutan suara 2019.
                valid_until=date(2019, 1, 1),
            ),
            Region(
                region_code="00.01.02",
                region_name="Kecamatan Uji Baru",
                region_level=RegionLevel.DISTRICT,
                parent_id=kabupaten.id,
                valid_from=date(2019, 1, 2),
            ),
        ]
    )
    await session.flush()


async def test_katalog_memuat_kontestasi_partai_dan_paslon(
    session: AsyncSession, tmp_path: Path
) -> None:
    await _isi_referensi(session, tmp_path)
    catalog = await load_catalog(session)

    assert {(t, y) for t in ElectionType for y in (2019, 2024)} <= catalog.elections
    assert catalog.party_years["UJI_A"] == {2019, 2024}
    assert catalog.party_years["UJI_B"] == {2019}
    assert catalog.party_years["UJI_C"] == {2024}
    assert {(2019, 1), (2019, 2), (2024, 1), (2024, 2)} <= catalog.candidate_pairs


async def test_katalog_wilayah_mengikuti_masa_berlaku(
    session: AsyncSession, tmp_path: Path
) -> None:
    await _isi_referensi(session, tmp_path)
    catalog = await load_catalog(session)

    assert catalog.regions[DPR_2019]["00"] is RegionLevel.PROVINCE
    assert catalog.regions[DPR_2019]["00.01.01"] is RegionLevel.DISTRICT
    assert "00.01.02" not in catalog.regions[DPR_2019]
    assert "00.01.01" not in catalog.regions[DPR_2024]
    assert catalog.regions[DPR_2024]["00.01.02"] is RegionLevel.DISTRICT


async def test_validasi_berkas_terhadap_database(session: AsyncSession, tmp_path: Path) -> None:
    await _isi_referensi(session, tmp_path / "ref")
    catalog = await load_catalog(session)

    lolos = validate_file(
        tulis_csv(
            tmp_path / "dpr2024.csv",
            [suara_partai("00.01.02", "UJI_A", "10"), suara_partai("00.01", "UJI_C", "4")],
        ),
        catalog,
    )
    assert lolos.passed, lolos.errors

    gagal = validate_file(
        tulis_csv(tmp_path / "pilpres2024.csv", [suara_paslon("00.01.01", "2")]), catalog
    )
    assert any("tidak berlaku pada Pemilu 2024" in e for e in gagal.errors)
