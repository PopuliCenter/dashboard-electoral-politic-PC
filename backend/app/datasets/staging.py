"""Memuat berkas impor yang sudah divalidasi ke database staging (T3.4).

Fungsi di sini tidak tahu database mana yang ia tulis; yang menjamin ini hanya
staging adalah CLI (`python -m app.datasets load`), yang menolak jalan bila URL
staging kosong atau sama dengan URL produksi.

Hanya berkas yang lolos validasi T3.1 yang menjadi versi dataset. Berkas yang
gagal tidak menghasilkan versi maupun baris hasil; percobaannya tetap tercatat
di `ingestion_jobs` (status failed) dan `audit_logs` beserta ringkasan galatnya.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import (
    DatasetError,
    ResultRow,
    check_conflicts,
    delete_rows,
    describe,
    replacement_warnings,
    version_scope,
)
from app.importer.validator import CandidateVote, PartyVote, Turnout, ValidationReport
from app.models import (
    AuditLog,
    CandidatePair,
    CandidateResult,
    DatasetVersion,
    DataSource,
    Election,
    ElectionResult,
    IngestionJob,
    Party,
    Region,
    RegionTurnout,
)
from app.models.enums import DataStatus, JobStatus, ValidationStatus

# Ringkasan galat validasi yang disimpan di audit log percobaan yang gagal.
MAX_ERRORS_STORED = 50


@dataclass(frozen=True)
class SourceInfo:
    """Asal data. `source_name` adalah kuncinya; `source_type` wajib saat sumber baru."""

    source_name: str
    source_type: str | None = None
    source_url: str | None = None
    collection_method: str | None = None
    retrieved_at: datetime | None = None


@dataclass
class LoadResult:
    # None bila validasi gagal: tidak ada versi yang dibuat.
    version: DatasetVersion | None
    record_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Sumber, kontestasi, wilayah
# --------------------------------------------------------------------------- #


async def _source(session: AsyncSession, info: SourceInfo) -> DataSource:
    existing = await session.scalar(
        select(DataSource).where(DataSource.source_name == info.source_name)
    )
    if existing is None:
        if not info.source_type:
            raise DatasetError(
                [
                    f"sumber {info.source_name!r} belum ada; "
                    "source_type wajib diisi untuk sumber baru"
                ]
            )
        source = DataSource(
            source_name=info.source_name,
            source_type=info.source_type,
            source_url=info.source_url,
            collection_method=info.collection_method,
            retrieved_at=info.retrieved_at,
        )
        session.add(source)
        await session.flush()
        return source

    # Asal-usul tidak boleh berubah diam-diam: nilai yang diberikan harus sama
    # dengan yang tercatat. Nilai yang tidak diberikan memakai yang tercatat.
    conflicts = [
        f"{name}: tercatat {stored!r}, diberikan {given!r}"
        for name, stored, given in (
            ("source_type", existing.source_type, info.source_type),
            ("source_url", existing.source_url, info.source_url),
            ("collection_method", existing.collection_method, info.collection_method),
            ("retrieved_at", existing.retrieved_at, info.retrieved_at),
        )
        if given is not None and given != stored
    ]
    if conflicts:
        raise DatasetError(
            [
                f"sumber {info.source_name!r} sudah ada dengan metadata berbeda; "
                "pakai nama sumber baru bila dokumennya memang lain",
                *conflicts,
            ]
        )
    return existing


async def _election(session: AsyncSession, report: ValidationReport) -> Election:
    assert report.election is not None
    election_type, year = report.election
    election = await session.scalar(
        select(Election).where(
            Election.election_type == election_type, Election.election_year == year
        )
    )
    if election is None or election.election_date is None:
        raise DatasetError(
            [f"kontestasi {election_type.value} {year} tidak ada atau belum bertanggal di database"]
        )
    return election


async def _region_ids(
    session: AsyncSession, election: Election, codes: set[str]
) -> dict[str, uuid.UUID]:
    """Kode wilayah -> id wilayah yang berlaku pada hari pemungutan suara."""
    rows = await session.execute(
        select(Region.region_code, Region.id).where(
            Region.region_code.in_(codes),
            Region.valid_from <= election.election_date,
            or_(Region.valid_until.is_(None), Region.valid_until >= election.election_date),
        )
    )
    found: dict[str, uuid.UUID] = {}
    for code, region_id in rows.tuples().all():
        if code in found:
            raise DatasetError([f"kode wilayah {code} punya dua versi yang berlaku bersamaan"])
        found[code] = region_id
    missing = codes - found.keys()
    if missing:
        # Validator sudah memeriksa ini; sampai di sini berarti katalog yang dipakai
        # validator berbeda dengan isi database yang ditulis.
        raise DatasetError(
            [f"kode wilayah tidak ditemukan di database: {', '.join(sorted(missing))}"]
        )
    return found


async def _check_same_scope_as_before(
    session: AsyncSession, dataset_name: str, report: ValidationReport, election: Election
) -> None:
    """Versi baru sebuah dataset harus berisi jenis data dan kontestasi yang sama."""
    previous = await session.scalar(
        select(DatasetVersion.id)
        .where(DatasetVersion.dataset_name == dataset_name)
        .order_by(DatasetVersion.version_number.desc())
        .limit(1)
    )
    if previous is None:
        return
    scope = await version_scope(session, previous)
    if scope is None:
        return
    if scope.kind is not report.kind or scope.election.id != election.id:
        raise DatasetError(
            [
                f"dataset {dataset_name!r} berisi {describe(scope)}, sedangkan berkas ini "
                f"{report.kind} {election.election_type.value} {election.election_year}; "
                "pakai nama dataset lain"
            ]
        )


# --------------------------------------------------------------------------- #
# Baris hasil
# --------------------------------------------------------------------------- #


async def _build_rows(
    session: AsyncSession,
    report: ValidationReport,
    election: Election,
    version: DatasetVersion,
    status: DataStatus,
) -> list[ResultRow]:
    regions = await _region_ids(session, election, {r.region_code for r in report.records})
    common = {
        "election_id": election.id,
        "source_id": version.source_id,
        "dataset_version_id": version.id,
        "data_status": status,
    }

    party_codes = {r.party_code for r in report.records if isinstance(r, PartyVote)}
    parties = dict(
        (
            await session.execute(
                select(Party.party_code, Party.id).where(Party.party_code.in_(party_codes))
            )
        )
        .tuples()
        .all()
    )
    pairs = dict(
        (
            await session.execute(
                select(CandidatePair.pair_number, CandidatePair.id).where(
                    CandidatePair.election_id == election.id
                )
            )
        )
        .tuples()
        .all()
    )

    rows: list[ResultRow] = []
    for r in report.records:
        region_id = regions[r.region_code]
        if isinstance(r, PartyVote):
            rows.append(
                ElectionResult(
                    **common,
                    region_id=region_id,
                    party_id=parties[r.party_code],
                    vote_count=r.vote_count,
                )
            )
        elif isinstance(r, CandidateVote):
            rows.append(
                CandidateResult(
                    **common,
                    region_id=region_id,
                    candidate_pair_id=pairs[r.pair_number],
                    vote_count=r.vote_count,
                )
            )
        elif isinstance(r, Turnout):
            rows.append(
                RegionTurnout(
                    **common,
                    region_id=region_id,
                    registered_voters=r.registered_voters,
                    voters_turned_out=r.voters_turned_out,
                    valid_votes=r.valid_votes,
                    invalid_votes=r.invalid_votes,
                )
            )
    return rows


# --------------------------------------------------------------------------- #
# API publik
# --------------------------------------------------------------------------- #


async def load_into_staging(
    session: AsyncSession,
    report: ValidationReport,
    *,
    dataset_name: str,
    source: SourceInfo,
    file_reference: str,
) -> LoadResult:
    """Catat satu percobaan muat; bila lolos validasi, tulis versi dan barisnya.

    Tidak melakukan commit: pemanggil yang memutuskan commit atau rollback.
    """
    started = datetime.now(UTC)
    audit: dict[str, object] = {
        "dataset_name": dataset_name,
        "file": file_reference,
        "sha256": report.checksum,
        "kind": report.kind.value if report.kind else None,
        "warnings": len(report.warnings),
    }

    if not report.passed or report.data_status is None:
        # Percobaan gagal tetap dicatat, tetapi tidak membuat sumber baru: sumber
        # yang tercatat hanya sumber yang benar-benar menghasilkan data.
        known_source = await session.scalar(
            select(DataSource.id).where(DataSource.source_name == source.source_name)
        )
        session.add(
            IngestionJob(
                job_type="load_staging",
                status=JobStatus.FAILED,
                source_id=known_source,
                started_at=started,
                finished_at=datetime.now(UTC),
                record_count=0,
                message=f"validasi gagal: {len(report.errors)} kesalahan",
            )
        )
        session.add(
            AuditLog(
                action="dataset.load_staging_rejected",
                entity_type="dataset_versions",
                payload={
                    **audit,
                    "source_name": source.source_name,
                    "errors": report.errors[:MAX_ERRORS_STORED],
                },
            )
        )
        await session.flush()
        return LoadResult(None, 0, list(report.errors), list(report.warnings))

    data_source = await _source(session, source)
    election = await _election(session, report)
    await _check_same_scope_as_before(session, dataset_name, report, election)

    last_number = await session.scalar(
        select(func.max(DatasetVersion.version_number)).where(
            DatasetVersion.dataset_name == dataset_name
        )
    )
    version = DatasetVersion(
        source_id=data_source.id,
        dataset_name=dataset_name,
        version_number=(last_number or 0) + 1,
        collected_at=source.retrieved_at or data_source.retrieved_at,
        record_count=len(report.records),
        # Lolos validasi format saja. Hanya rekonsiliasi T3.3 yang boleh mengubahnya
        # menjadi `passed`; sampai itu ada, promosi ditahan (keputusan pengguna).
        validation_status=ValidationStatus.PENDING,
        data_status=report.data_status,
        file_reference=f"{file_reference} sha256:{report.checksum}",
    )
    session.add(version)
    await session.flush()

    # Versi baru menggantikan baris versi lama dataset yang sama, persis seperti
    # di produksi: staging memakai skema yang sama, dengan UNIQUE yang sama.
    assert report.kind is not None
    earlier = list(
        (
            await session.scalars(
                select(DatasetVersion).where(
                    DatasetVersion.dataset_name == dataset_name, DatasetVersion.id != version.id
                )
            )
        ).all()
    )
    rows = await _build_rows(session, report, election, version, report.data_status)
    replacement = await replacement_warnings(
        session, report.kind, earlier, rows, report.data_status, where="staging"
    )
    replaced = await delete_rows(session, report.kind, [v.id for v in earlier]) if earlier else 0
    await check_conflicts(session, report.kind, election.id, rows, where="staging")
    session.add_all(rows)
    session.add(
        IngestionJob(
            job_type="load_staging",
            status=JobStatus.SUCCEEDED,
            source_id=data_source.id,
            dataset_version_id=version.id,
            started_at=started,
            finished_at=datetime.now(UTC),
            record_count=len(rows),
        )
    )
    session.add(
        AuditLog(
            action="dataset.load_staging",
            entity_type="dataset_versions",
            entity_id=version.id,
            payload={
                **audit,
                "version_number": version.version_number,
                "record_count": len(rows),
                "replaced": replaced,
                "replacement_warnings": replacement,
            },
        )
    )
    await session.flush()
    return LoadResult(version, len(rows), [], [*replacement, *report.warnings])
