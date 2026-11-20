"""Muat ke staging dan promosi staging -> produksi (T3.4).

Dua database sungguhan: `staging_session` (STAGING_DATABASE_URL) dan `session`
(DATABASE_URL, berperan sebagai produksi). Keduanya di-rollback, dan semua data
fiktif (aturan data 2). Referensi fiktif diisi terpisah ke tiap database, jadi
UUID-nya berbeda: promosi harus memetakan lewat kunci alami.
"""

import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import DatasetError, delete_rows
from app.datasets.promotion import promote_version
from app.datasets.staging import LoadResult, SourceInfo, load_into_staging
from app.datasets.withdraw import check_admin, withdraw_version
from app.importer.catalog import load_catalog
from app.importer.format import RecordKind
from app.importer.validator import validate_file
from app.models import (
    AuditLog,
    CandidatePair,
    CandidateResult,
    DatasetVersion,
    DataSource,
    ElectionResult,
    IngestionJob,
    Party,
    Region,
    RegionTurnout,
    User,
)
from app.models.enums import DataStatus, JobStatus, RegionLevel, RoleCode, ValidationStatus
from app.services import auth
from tests.import_fixtures import (
    isi_referensi_fiktif,
    partisipasi,
    suara_partai,
    suara_paslon,
    tulis_csv,
)

pytestmark = pytest.mark.integration

SUMBER = SourceInfo(
    source_name="Dokumen Uji T3.4",
    source_type="uji",
    source_url="https://kpu-uji.invalid/rekap.pdf",
)
DATASET = "uji-dpr-2024"


@pytest.fixture
async def dua_db(
    staging_session: AsyncSession, session: AsyncSession, tmp_path: Path
) -> tuple[AsyncSession, AsyncSession]:
    await isi_referensi_fiktif(staging_session, tmp_path / "ref-staging")
    await isi_referensi_fiktif(session, tmp_path / "ref-produksi")
    return staging_session, session


async def _muat(
    staging: AsyncSession,
    path: Path,
    rows: list[dict[str, str]],
    *,
    dataset: str = DATASET,
    source: SourceInfo = SUMBER,
    rekonsiliasi_lolos: bool = True,
) -> LoadResult:
    """Muat ke staging. Secara bawaan juga mensimulasikan rekonsiliasi T3.3 yang
    lolos (status `passed`), karena T3.3 belum ada dan test promosi butuh itu.
    Pakai `rekonsiliasi_lolos=False` untuk melihat status asli hasil muat."""
    report = validate_file(tulis_csv(path, rows), await load_catalog(staging))
    hasil = await load_into_staging(
        staging, report, dataset_name=dataset, source=source, file_reference=path.name
    )
    if hasil.version is not None and rekonsiliasi_lolos:
        hasil.version.validation_status = ValidationStatus.PASSED
        await staging.flush()
    return hasil


def _dpr(*suara: tuple[str, str, str]) -> list[dict[str, str]]:
    return [suara_partai(region, party, votes) for region, party, votes in suara]


async def _id_wilayah(db: AsyncSession, code: str) -> uuid.UUID:
    region_id = await db.scalar(select(Region.id).where(Region.region_code == code))
    assert region_id is not None
    return region_id


async def _id_partai(db: AsyncSession, code: str) -> uuid.UUID:
    party_id = await db.scalar(select(Party.id).where(Party.party_code == code))
    assert party_id is not None
    return party_id


async def _suara_produksi(db: AsyncSession, version_id: uuid.UUID) -> dict[tuple[str, str], int]:
    rows = await db.execute(
        select(Region.region_code, Party.party_code, ElectionResult.vote_count)
        .join(Region, ElectionResult.region_id == Region.id)
        .join(Party, ElectionResult.party_id == Party.id)
        .where(ElectionResult.dataset_version_id == version_id)
    )
    return {(r, p): v for r, p, v in rows.tuples().all()}


# --------------------------------------------------------------------------- #
# Muat ke staging
# --------------------------------------------------------------------------- #


async def test_muat_berkas_lolos_menjadi_versi_dengan_barisnya(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, _ = dua_db
    hasil = await _muat(
        staging,
        tmp_path / "dpr.csv",
        _dpr(("00.01.02", "UJI_A", "10"), ("00.01", "UJI_C", "4")),
        rekonsiliasi_lolos=False,
    )

    assert hasil.version is not None
    v = hasil.version
    assert (v.dataset_name, v.version_number, v.record_count) == (DATASET, 1, 2)
    # Lolos validasi format saja; hanya rekonsiliasi T3.3 yang boleh membuatnya passed.
    assert v.validation_status is ValidationStatus.PENDING
    assert v.data_status is DataStatus.OFFICIAL
    assert v.file_reference is not None and v.file_reference.startswith("dpr.csv sha256:")

    rows = (
        await staging.scalars(
            select(ElectionResult).where(ElectionResult.dataset_version_id == v.id)
        )
    ).all()
    assert {(r.vote_count, r.data_status, r.source_id) for r in rows} == {
        (10, DataStatus.OFFICIAL, v.source_id),
        (4, DataStatus.OFFICIAL, v.source_id),
    }
    job = await staging.scalar(select(IngestionJob).where(IngestionJob.dataset_version_id == v.id))
    assert job is not None and job.status is JobStatus.SUCCEEDED and job.record_count == 2
    audit = await staging.scalar(select(AuditLog).where(AuditLog.entity_id == v.id))
    assert audit is not None and audit.action == "dataset.load_staging"


async def test_berkas_gagal_validasi_tidak_menjadi_versi(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, _ = dua_db
    hasil = await _muat(staging, tmp_path / "salah.csv", _dpr(("00.01.02", "UJI_B", "10")))

    assert hasil.version is None
    assert any("UJI_B tidak ikut Pemilu 2024" in e for e in hasil.errors)
    assert (
        await staging.scalar(select(DatasetVersion).where(DatasetVersion.dataset_name == DATASET))
    ) is None
    audit = (
        await staging.scalars(
            select(AuditLog).where(AuditLog.action == "dataset.load_staging_rejected")
        )
    ).all()
    assert any(a.payload and a.payload.get("file") == "salah.csv" for a in audit)
    # Percobaan gagal tidak meninggalkan sumber baru yang permanen.
    assert (
        await staging.scalar(select(DataSource).where(DataSource.source_name == SUMBER.source_name))
    ) is None


async def test_percobaan_gagal_dengan_sumber_baru_tanpa_jenis_tetap_tercatat(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, _ = dua_db
    hasil = await _muat(
        staging,
        tmp_path / "salah.csv",
        _dpr(("00.01.02", "UJI_B", "10")),
        source=SourceInfo(source_name="Sumber Uji Tanpa Jenis"),
    )
    assert hasil.version is None
    audit = (
        await staging.scalars(
            select(AuditLog).where(AuditLog.action == "dataset.load_staging_rejected")
        )
    ).all()
    assert any(
        a.payload and a.payload.get("source_name") == "Sumber Uji Tanpa Jenis" for a in audit
    )


async def test_muat_ulang_menambah_nomor_versi(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, _ = dua_db
    v1 = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    v2 = await _muat(staging, tmp_path / "b.csv", _dpr(("00.01.02", "UJI_A", "11")))
    assert v1.version is not None and v2.version is not None
    assert (v1.version.version_number, v2.version.version_number) == (1, 2)
    # Staging memakai UNIQUE yang sama: baris v1 digantikan baris v2.
    sisa = (
        await staging.scalars(
            select(ElectionResult.dataset_version_id).where(
                ElectionResult.dataset_version_id.in_([v1.version.id, v2.version.id])
            )
        )
    ).all()
    assert sisa == [v2.version.id]


async def test_satu_nama_dataset_tidak_boleh_berganti_kontestasi(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, _ = dua_db
    await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    with pytest.raises(DatasetError, match="pakai nama dataset lain"):
        await _muat(staging, tmp_path / "b.csv", [suara_paslon("00.01.02", "1", "5")])


async def test_sumber_baru_wajib_punya_jenis(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, _ = dua_db
    with pytest.raises(DatasetError, match="source_type wajib"):
        await _muat(
            staging,
            tmp_path / "a.csv",
            _dpr(("00.01.02", "UJI_A", "10")),
            source=SourceInfo(source_name="Sumber Uji Tanpa Jenis"),
        )


async def test_metadata_sumber_tidak_boleh_berubah_diam_diam(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, _ = dua_db
    await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    lain = SourceInfo(source_name=SUMBER.source_name, source_url="https://kpu-uji.invalid/lain")
    with pytest.raises(DatasetError, match="metadata berbeda"):
        await _muat(staging, tmp_path / "b.csv", _dpr(("00.01.02", "UJI_A", "10")), source=lain)
    # Nama saja cukup untuk memakai sumber yang sudah tercatat.
    hasil = await _muat(
        staging,
        tmp_path / "c.csv",
        _dpr(("00.01.02", "UJI_A", "10")),
        source=SourceInfo(source_name=SUMBER.source_name),
    )
    assert hasil.version is not None


# --------------------------------------------------------------------------- #
# Promosi
# --------------------------------------------------------------------------- #


async def test_promosi_menyalin_versi_dan_memetakan_referensi(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    # UUID referensi di kedua database memang berbeda.
    assert await _id_wilayah(staging, "00.01.02") != await _id_wilayah(produksi, "00.01.02")
    assert await _id_partai(staging, "UJI_A") != await _id_partai(produksi, "UJI_A")

    hasil = await _muat(
        staging, tmp_path / "dpr.csv", _dpr(("00.01.02", "UJI_A", "10"), ("00.01", "UJI_C", "4"))
    )
    assert hasil.version is not None
    laporan = await promote_version(staging, produksi, hasil.version.id)

    assert (laporan.inserted, laporan.replaced) == (2, 0)
    salinan = await produksi.get(DatasetVersion, hasil.version.id)
    assert salinan is not None and salinan.validation_status is ValidationStatus.PASSED
    sumber = await produksi.get(DataSource, salinan.source_id)
    assert sumber is not None and sumber.source_name == SUMBER.source_name
    assert await _suara_produksi(produksi, hasil.version.id) == {
        ("00.01.02", "UJI_A"): 10,
        ("00.01", "UJI_C"): 4,
    }
    audit = await produksi.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == hasil.version.id, AuditLog.action == "dataset.promote"
        )
    )
    assert audit is not None


async def test_versi_yang_sama_tidak_bisa_dipromosikan_dua_kali(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    hasil = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    assert hasil.version is not None
    await promote_version(staging, produksi, hasil.version.id)
    with pytest.raises(DatasetError, match="sudah dipromosikan"):
        await promote_version(staging, produksi, hasil.version.id)


async def test_versi_baru_menggantikan_baris_versi_lama(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    v1 = await _muat(
        staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10"), ("00.01", "UJI_A", "10"))
    )
    assert v1.version is not None
    await promote_version(staging, produksi, v1.version.id)
    v2 = await _muat(staging, tmp_path / "b.csv", _dpr(("00.01.02", "UJI_A", "12")))
    assert v2.version is not None
    laporan = await promote_version(staging, produksi, v2.version.id)

    assert (laporan.inserted, laporan.replaced, laporan.replaced_versions) == (1, 2, [1])
    assert await _suara_produksi(produksi, v1.version.id) == {}
    assert await _suara_produksi(produksi, v2.version.id) == {("00.01.02", "UJI_A"): 12}
    # Versi lama tetap tercatat sebagai riwayat.
    assert await produksi.get(DatasetVersion, v1.version.id) is not None


async def test_versi_yang_sudah_digantikan_tidak_bisa_dipromosikan(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    v1 = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    v2 = await _muat(staging, tmp_path / "b.csv", _dpr(("00.01.02", "UJI_A", "12")))
    assert v1.version is not None and v2.version is not None
    with pytest.raises(DatasetError, match="digantikan versi yang lebih baru"):
        await promote_version(staging, produksi, v1.version.id)
    await promote_version(staging, produksi, v2.version.id)
    with pytest.raises(DatasetError, match="lebih lama dan tidak boleh menimpanya"):
        await promote_version(staging, produksi, v1.version.id)


async def test_dataset_lain_untuk_sel_yang_sama_ditolak_saat_muat(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, _ = dua_db
    await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    with pytest.raises(DatasetError, match=f"bertabrakan dengan dataset {DATASET} v1"):
        await _muat(
            staging,
            tmp_path / "b.csv",
            [suara_partai("00.01.02", "UJI_A", "9", status="unofficial")],
            dataset="uji-dpr-2024-sirekap",
        )


async def test_dataset_lain_untuk_sel_yang_sama_ditolak_saat_promosi(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    """Staging bisa menyimpang dari produksi (misalnya setelah dikosongkan)."""
    staging, produksi = dua_db
    resmi = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    assert resmi.version is not None
    await promote_version(staging, produksi, resmi.version.id)
    await delete_rows(staging, RecordKind.PARTY_VOTES, [resmi.version.id])

    sirekap = await _muat(
        staging,
        tmp_path / "b.csv",
        [suara_partai("00.01.02", "UJI_A", "9", status="unofficial")],
        dataset="uji-dpr-2024-sirekap",
    )
    assert sirekap.version is not None
    with pytest.raises(DatasetError, match="sudah ada di produksi"):
        await promote_version(staging, produksi, sirekap.version.id)
    assert await produksi.get(DatasetVersion, sirekap.version.id) is None


async def test_referensi_yang_tidak_ada_di_produksi_menolak_promosi(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    staging.add(
        Region(
            region_code="00.01.09",
            region_name="Kecamatan Uji Hanya di Staging",
            region_level=RegionLevel.DISTRICT,
            parent_id=await _id_wilayah(staging, "00.01"),
            valid_from=date(2019, 1, 2),
        )
    )
    await staging.flush()
    hasil = await _muat(
        staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10"), ("00.01.09", "UJI_A", "3"))
    )
    assert hasil.version is not None
    with pytest.raises(DatasetError, match="wilayah belum ada di produksi: 00.01.09"):
        await promote_version(staging, produksi, hasil.version.id)
    assert await produksi.get(DatasetVersion, hasil.version.id) is None


async def test_hanya_versi_passed_yang_boleh_dipromosikan(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    hasil = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    assert hasil.version is not None
    hasil.version.validation_status = ValidationStatus.FAILED
    await staging.flush()
    with pytest.raises(DatasetError, match="hanya versi passed"):
        await promote_version(staging, produksi, hasil.version.id)


async def test_versi_tidak_dikenal_ditolak(dua_db: tuple[AsyncSession, AsyncSession]) -> None:
    staging, produksi = dua_db
    with pytest.raises(DatasetError, match="tidak ada di staging"):
        await promote_version(staging, produksi, uuid.uuid4())


async def test_promosi_suara_paslon(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    hasil = await _muat(
        staging,
        tmp_path / "pilpres.csv",
        [suara_paslon("00.01.02", "1", "7"), suara_paslon("00.01.02", "2", "5")],
        dataset="uji-pilpres-2024",
    )
    assert hasil.version is not None
    laporan = await promote_version(staging, produksi, hasil.version.id)
    assert laporan.inserted == 2

    rows = await produksi.execute(
        select(CandidatePair.pair_number, CandidateResult.vote_count)
        .join(CandidatePair, CandidateResult.candidate_pair_id == CandidatePair.id)
        .where(CandidateResult.dataset_version_id == hasil.version.id)
    )
    assert dict(rows.tuples().all()) == {1: 7, 2: 5}


async def test_promosi_partisipasi_mempertahankan_angka_tidak_tersedia(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    hasil = await _muat(
        staging,
        tmp_path / "partisipasi.csv",
        [partisipasi("00.01.02", dpt="", hadir="800", sah="780", tidak_sah="20")],
        dataset="uji-partisipasi-dpr-2024",
    )
    assert hasil.version is not None
    await promote_version(staging, produksi, hasil.version.id)

    row = await produksi.scalar(
        select(RegionTurnout).where(RegionTurnout.dataset_version_id == hasil.version.id)
    )
    assert row is not None
    assert (row.registered_voters, row.voters_turned_out, row.valid_votes, row.invalid_votes) == (
        None,
        800,
        780,
        20,
    )


# --------------------------------------------------------------------------- #
# Review T3.4: rekonsiliasi, peringatan penggantian, masa berlaku wilayah
# --------------------------------------------------------------------------- #


async def test_versi_pending_ditahan_sampai_rekonsiliasi(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    hasil = await _muat(
        staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")), rekonsiliasi_lolos=False
    )
    assert hasil.version is not None
    with pytest.raises(DatasetError, match="belum direkonsiliasi"):
        await promote_version(staging, produksi, hasil.version.id)
    assert await produksi.get(DatasetVersion, hasil.version.id) is None


async def test_versi_tidak_resmi_menggantikan_resmi_dengan_peringatan(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    v1 = await _muat(
        staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10"), ("00.01", "UJI_C", "4"))
    )
    assert v1.version is not None
    await promote_version(staging, produksi, v1.version.id)

    v2 = await _muat(
        staging,
        tmp_path / "b.csv",
        [
            suara_partai("00.01.02", "UJI_A", "99", status="unofficial"),
            suara_partai("00.01", "UJI_C", "1", status="unofficial"),
        ],
    )
    assert v2.version is not None
    assert any("official -> unofficial" in w and "staging" in w for w in v2.warnings)

    laporan = await promote_version(staging, produksi, v2.version.id)
    assert any("official -> unofficial" in w and "produksi" in w for w in laporan.warnings)
    audit = await produksi.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == v2.version.id, AuditLog.action == "dataset.promote"
        )
    )
    assert audit is not None and audit.payload is not None
    assert audit.payload["replacement_warnings"] == laporan.warnings


async def test_versi_lebih_sempit_menggantikan_dengan_peringatan(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    v1 = await _muat(
        staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10"), ("00.01", "UJI_A", "10"))
    )
    assert v1.version is not None
    await promote_version(staging, produksi, v1.version.id)

    v2 = await _muat(staging, tmp_path / "b.csv", _dpr(("00.01.02", "UJI_A", "12")))
    assert v2.version is not None
    pesan = [w for w in v2.warnings if "lebih sedikit di staging" in w]
    assert pesan and "1 dari 2 baris" in pesan[0] and "00.01" in pesan[0]

    laporan = await promote_version(staging, produksi, v2.version.id)
    pesan = [w for w in laporan.warnings if "lebih sedikit di produksi" in w]
    assert pesan and "1 wilayah hilang seluruhnya: 00.01" in pesan[0]
    assert await _suara_produksi(produksi, v2.version.id) == {("00.01.02", "UJI_A"): 12}


async def test_versi_pengganti_yang_sama_luasnya_tanpa_peringatan(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    v1 = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    assert v1.version is not None
    await promote_version(staging, produksi, v1.version.id)
    v2 = await _muat(staging, tmp_path / "b.csv", _dpr(("00.01.02", "UJI_A", "11")))
    assert v2.version is not None and v2.warnings == []
    laporan = await promote_version(staging, produksi, v2.version.id)
    assert laporan.warnings == []


async def test_wilayah_produksi_yang_tidak_berlaku_menolak_promosi(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    wilayah = await produksi.get(Region, await _id_wilayah(produksi, "00.01.02"))
    assert wilayah is not None
    wilayah.valid_until = date(2023, 12, 31)  # sebelum pemungutan suara 2024-01-01
    await produksi.flush()

    hasil = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    assert hasil.version is not None
    with pytest.raises(DatasetError, match="tidak berlaku pada hari pemungutan suara"):
        await promote_version(staging, produksi, hasil.version.id)


async def test_versi_yang_sudah_lama_digantikan_tidak_memicu_peringatan_palsu(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    """v1 unofficial -> v2 official -> v3 official: v3 tidak mengubah status apa pun."""
    staging, produksi = dua_db
    baris = [suara_partai("00.01.02", "UJI_A", "10", status="unofficial")]
    v1 = await _muat(staging, tmp_path / "a.csv", baris)
    v2 = await _muat(staging, tmp_path / "b.csv", _dpr(("00.01.02", "UJI_A", "11")))
    v3 = await _muat(staging, tmp_path / "c.csv", _dpr(("00.01.02", "UJI_A", "12")))
    assert v1.version and v2.version and v3.version
    assert any("unofficial -> official" in w for w in v2.warnings)
    assert v3.warnings == []

    # Di produksi pun sama, setelah v1 dan v2 pernah dipromosikan.
    v4 = await _muat(staging, tmp_path / "d.csv", baris)
    assert v4.version is not None
    await promote_version(staging, produksi, v4.version.id)
    v5 = await _muat(staging, tmp_path / "e.csv", _dpr(("00.01.02", "UJI_A", "13")))
    assert v5.version is not None
    laporan_v5 = await promote_version(staging, produksi, v5.version.id)
    assert any("unofficial -> official" in w for w in laporan_v5.warnings)
    v6 = await _muat(staging, tmp_path / "f.csv", _dpr(("00.01.02", "UJI_A", "14")))
    assert v6.version is not None
    assert (await promote_version(staging, produksi, v6.version.id)).warnings == []


# --------------------------------------------------------------------------- #
# Review T5.3: penarikan versi dan salinan catatan muat
# --------------------------------------------------------------------------- #


async def _admin(session: AsyncSession, email: str = "admin-tarik@uji.invalid") -> User:
    return await auth.create_user(
        session, email, "Admin Uji", "kata-sandi-uji-panjang", RoleCode.ADMIN
    )


async def test_promosi_menyalin_catatan_muat_dari_staging(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    hasil = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    assert hasil.version is not None
    await promote_version(staging, produksi, hasil.version.id)
    salinan = await produksi.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == hasil.version.id, AuditLog.action == "dataset.load_staging"
        )
    )
    assert salinan is not None and salinan.payload is not None
    assert salinan.payload["copied_from"] == "staging"
    assert salinan.payload["file"] == "a.csv"


async def test_tabrakan_menunjuk_perintah_tarik_yang_ada(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, _ = dua_db
    resmi = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    assert resmi.version is not None
    with pytest.raises(DatasetError) as info:
        await _muat(
            staging,
            tmp_path / "b.csv",
            [suara_partai("00.01.02", "UJI_A", "9", status="unofficial")],
            dataset="uji-dpr-2024-sirekap",
        )
    assert f"python -m app.datasets withdraw {resmi.version.id} --db staging" in str(info.value)


async def test_tarik_versi_lalu_dataset_lain_bisa_dipromosikan(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    admin = await _admin(produksi)
    resmi = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    assert resmi.version is not None
    await promote_version(staging, produksi, resmi.version.id)

    laporan = await withdraw_version(
        produksi,
        resmi.version.id,
        reason="Diganti data Sirekap atas keputusan tim",
        actor=admin,
        actor_email=admin.email,
    )
    assert laporan.deleted == 1
    assert await _suara_produksi(produksi, resmi.version.id) == {}
    assert await produksi.get(DatasetVersion, resmi.version.id) is not None  # riwayat tetap
    jejak = await produksi.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == resmi.version.id, AuditLog.action == "dataset.withdraw"
        )
    )
    assert jejak is not None and jejak.actor_user_id == admin.id
    assert jejak.payload is not None and "Sirekap" in jejak.payload["reason"]

    with pytest.raises(DatasetError, match="sudah ditarik"):
        await withdraw_version(
            produksi,
            resmi.version.id,
            reason="alasan yang cukup panjang",
            actor=admin,
            actor_email=admin.email,
        )

    # Sel yang tadinya bertabrakan kini bebas di produksi.
    await delete_rows(staging, RecordKind.PARTY_VOTES, [resmi.version.id])
    sirekap = await _muat(
        staging,
        tmp_path / "b.csv",
        [suara_partai("00.01.02", "UJI_A", "9", status="unofficial")],
        dataset="uji-dpr-2024-sirekap",
    )
    assert sirekap.version is not None
    assert (await promote_version(staging, produksi, sirekap.version.id)).inserted == 1


async def test_tarik_butuh_admin_dan_alasan(
    dua_db: tuple[AsyncSession, AsyncSession], tmp_path: Path
) -> None:
    staging, produksi = dua_db
    peneliti = await auth.create_user(
        produksi,
        "peneliti-tarik@uji.invalid",
        "Peneliti",
        "kata-sandi-uji-panjang",
        RoleCode.RESEARCHER,
    )
    with pytest.raises(DatasetError, match="bukan Admin"):
        await check_admin(produksi, peneliti, peneliti.email)
    with pytest.raises(DatasetError, match="tidak ada"):
        await check_admin(produksi, None, "hantu@uji.invalid")

    hasil = await _muat(staging, tmp_path / "a.csv", _dpr(("00.01.02", "UJI_A", "10")))
    assert hasil.version is not None
    with pytest.raises(DatasetError, match="alasan wajib"):
        await withdraw_version(
            staging, hasil.version.id, reason="pendek", actor=None, actor_email="x@uji.invalid"
        )
