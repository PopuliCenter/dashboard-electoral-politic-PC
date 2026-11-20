"""Skema tabel inti pada database sungguhan (T2.1).

Data yang dipakai di sini jelas fiktif ("Partai A", kode wilayah uji) dan selalu
di-rollback, sesuai aturan data 2.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
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


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Sesi yang selalu di-rollback, jadi database uji tidak pernah berubah.

    Engine dibuat baru per test dengan NullPool: pytest-asyncio memakai event
    loop berbeda tiap test, dan koneksi asyncpg dari loop sebelumnya tidak bisa
    dipakai ulang.
    """
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        connection = await engine.connect()
    except (OSError, SQLAlchemyError) as exc:
        await engine.dispose()
        pytest.skip(f"database tidak tersedia: {type(exc).__name__}")

    transaction = await connection.begin()
    async_session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield async_session
    finally:
        await async_session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


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
        election_name="Pemilu Uji 2019",
        election_type=ElectionType.LEGISLATIVE_DPR,
        election_year=2019,
    )
    partai = Party(
        party_code=f"UJI-{uuid.uuid4().hex[:6]}",
        party_name="Partai A",
        contested_2019=True,
        contested_2024=True,
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
            election_name="Pemilu Uji 2019 (duplikat)",
            election_type=ElectionType.LEGISLATIVE_DPR,
            election_year=2019,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
