"""Skema tabel inti pada database sungguhan (T2.1).

Data yang dipakai di sini jelas fiktif ("Partai A", kode wilayah uji) dan selalu
di-rollback, sesuai aturan data 2.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Base,
    DatasetVersion,
    DataSource,
    Election,
    ElectionResult,
    Party,
    Region,
    RegionCrosswalk,
)
from app.models.enums import (
    CrosswalkRelation,
    DataStatus,
    ElectionType,
    RegionLevel,
    ValidationStatus,
)

pytestmark = pytest.mark.integration


async def test_semua_tabel_inti_sudah_dimigrasi(session: AsyncSession) -> None:
    hasil = await session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    )
    tabel_db = {baris[0] for baris in hasil}
    kurang = set(Base.metadata.tables) - tabel_db
    assert not kurang, f"tabel belum dimigrasi: {sorted(kurang)}"
    assert "alembic_version" in tabel_db


async def test_postgis_terpasang_dan_kolom_geometri_terdaftar(session: AsyncSession) -> None:
    versi = await session.scalar(text("SELECT PostGIS_Lib_Version()"))
    assert versi is not None

    srid = await session.scalar(
        text(
            "SELECT srid FROM geometry_columns "
            "WHERE f_table_name = 'regions' AND f_geometry_column = 'geometry'"
        )
    )
    assert srid == 4326


async def test_indeks_gist_terpasang_pada_geometri(session: AsyncSession) -> None:
    indeks = await session.scalar(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_regions_geometry'")
    )
    assert indeks is not None
    assert "gist" in indeks.lower()


# Tahun dan nomor urut fiktif. Database pengembangan berisi data referensi asli
# hasil seed T2.5 (kontestasi 2019 dan 2024, nomor urut partai 1 sampai 24), jadi
# data uji harus memakai nilai yang mustahil bentrok dengan data asli.
TAHUN_UJI = 2099
NOMOR_URUT_UJI = 901


async def _bibit_fiktif(session: AsyncSession) -> tuple[Region, Election, Party, DatasetVersion]:
    """Satu set data uji yang jelas fiktif."""
    sumber = DataSource(
        source_name=f"Dokumen uji {uuid.uuid4()}",
        source_type="uji",
        collection_method="manual",
    )
    session.add(sumber)
    await session.flush()

    versi = DatasetVersion(
        source_id=sumber.id,
        dataset_name=f"dataset-uji-{uuid.uuid4()}",
        version_number=1,
        validation_status=ValidationStatus.PASSED,
        data_status=DataStatus.OFFICIAL,
    )
    wilayah = Region(
        region_code="99",
        region_name="Provinsi Uji",
        region_level=RegionLevel.PROVINCE,
        valid_from=date(2019, 1, 1),
    )
    kontestasi = Election(
        election_name=f"Pemilu Uji {TAHUN_UJI}",
        election_type=ElectionType.LEGISLATIVE_DPR,
        election_year=TAHUN_UJI,
    )
    partai = Party(
        party_code=f"UJI-{uuid.uuid4().hex[:6]}",
        party_name="Partai A",
        contested_2019=True,
        contested_2024=True,
        ballot_number_2019=NOMOR_URUT_UJI,
        ballot_number_2024=NOMOR_URUT_UJI,
    )
    session.add_all([versi, wilayah, kontestasi, partai])
    await session.flush()
    return wilayah, kontestasi, partai, versi


async def test_suara_negatif_ditolak_database(session: AsyncSession) -> None:
    """Aturan data: angka suara tidak boleh negatif."""
    wilayah, kontestasi, partai, versi = await _bibit_fiktif(session)
    session.add(
        ElectionResult(
            election_id=kontestasi.id,
            region_id=wilayah.id,
            party_id=partai.id,
            vote_count=-1,
            source_id=versi.source_id,
            dataset_version_id=versi.id,
            data_status=DataStatus.OFFICIAL,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_hasil_ganda_untuk_kombinasi_sama_ditolak(session: AsyncSession) -> None:
    """Satu partai hanya punya satu baris per kontestasi per wilayah."""
    wilayah, kontestasi, partai, versi = await _bibit_fiktif(session)

    def baris() -> ElectionResult:
        return ElectionResult(
            election_id=kontestasi.id,
            region_id=wilayah.id,
            party_id=partai.id,
            vote_count=1000,
            source_id=versi.source_id,
            dataset_version_id=versi.id,
            data_status=DataStatus.OFFICIAL,
        )

    session.add(baris())
    await session.flush()
    session.add(baris())
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_hasil_tanpa_versi_dataset_ditolak(session: AsyncSession) -> None:
    """Aturan data 5: tidak ada baris hasil tanpa versi dataset."""
    wilayah, kontestasi, partai, versi = await _bibit_fiktif(session)
    session.add(
        ElectionResult(
            election_id=kontestasi.id,
            region_id=wilayah.id,
            party_id=partai.id,
            vote_count=1000,
            source_id=versi.source_id,
            dataset_version_id=None,
            data_status=DataStatus.OFFICIAL,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_kecamatan_wajib_punya_induk(session: AsyncSession) -> None:
    """Hanya provinsi yang boleh tanpa parent_id."""
    session.add(
        Region(
            region_code="9999999",
            region_name="Kecamatan Uji Tanpa Induk",
            region_level=RegionLevel.DISTRICT,
            valid_from=date(2024, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_padanan_wilayah_hanya_maju_dalam_waktu(session: AsyncSession) -> None:
    """from_year harus lebih awal dari to_year."""
    wilayah, _, _, _ = await _bibit_fiktif(session)
    session.add(
        RegionCrosswalk(
            from_region_id=wilayah.id,
            to_region_id=wilayah.id,
            from_year=2024,
            to_year=2019,
            relation=CrosswalkRelation.SAME,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_kontestasi_tidak_boleh_kembar(session: AsyncSession) -> None:
    """Satu jenis pemilu hanya punya satu baris per tahun."""
    await _bibit_fiktif(session)
    session.add(
        Election(
            election_name=f"Pemilu Uji {TAHUN_UJI} (duplikat)",
            election_type=ElectionType.LEGISLATIVE_DPR,
            election_year=TAHUN_UJI,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


def _partai_uji(**kolom: object) -> Party:
    nilai: dict[str, object] = {
        "party_code": f"UJI-{uuid.uuid4().hex[:6]}",
        "party_name": f"Partai Uji {uuid.uuid4().hex[:4]}",
    }
    nilai.update(kolom)
    return Party(**nilai)


@pytest.mark.parametrize(
    "kolom",
    [
        pytest.param(
            {"contested_2019": True, "ballot_number_2019": None},
            id="ikut-2019-tanpa-nomor-urut",
        ),
        pytest.param(
            {"contested_2024": True, "ballot_number_2024": 902, "ballot_number_2019": 902},
            id="tidak-ikut-2019-tetapi-punya-nomor-urut-2019",
        ),
        pytest.param({"contested_2019": True, "ballot_number_2019": 0}, id="nomor-urut-nol"),
        pytest.param({"contested_2024": True, "ballot_number_2024": -3}, id="nomor-urut-negatif"),
    ],
)
async def test_nomor_urut_harus_sesuai_keikutsertaan(
    session: AsyncSession, kolom: dict[str, object]
) -> None:
    """CHECK ini ditulis tangan di migrasi; autogenerate tidak bisa mendeteksinya."""
    session.add(_partai_uji(**kolom))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_nomor_urut_unik_per_tahun(session: AsyncSession) -> None:
    session.add(_partai_uji(contested_2019=True, ballot_number_2019=903))
    await session.flush()
    session.add(_partai_uji(contested_2019=True, ballot_number_2019=903))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_nomor_urut_sama_boleh_di_tahun_berbeda(session: AsyncSession) -> None:
    """Nomor 904 di 2019 dan nomor 904 di 2024 adalah dua hal yang tidak berhubungan."""
    session.add(_partai_uji(contested_2019=True, ballot_number_2019=904))
    session.add(_partai_uji(contested_2024=True, ballot_number_2024=904))
    await session.flush()


async def test_penukaran_nomor_urut_lolos_bila_keunikan_ditunda(session: AsyncSession) -> None:
    """Koreksi yang menukar nomor urut dua partai harus bisa dalam satu transaksi."""
    a = _partai_uji(contested_2019=True, ballot_number_2019=905)
    b = _partai_uji(contested_2019=True, ballot_number_2019=906)
    session.add_all([a, b])
    await session.flush()

    await session.execute(text("SET CONSTRAINTS uq_parties_ballot_number_2019 DEFERRED"))
    a.ballot_number_2019 = 906
    await session.flush()
    b.ballot_number_2019 = 905
    await session.flush()
    await session.execute(text("SET CONSTRAINTS uq_parties_ballot_number_2019 IMMEDIATE"))

    assert (a.ballot_number_2019, b.ballot_number_2019) == (906, 905)
