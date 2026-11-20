"""Promosi satu versi dataset dari staging ke produksi (T3.4).

Aturan:

- Hanya versi berstatus `passed` yang boleh dipromosikan (aturan data 6).
- Referensi dipetakan lewat kunci alami, bukan UUID: kontestasi lewat jenis dan
  tahun, partai lewat `party_code`, paslon lewat nomor urut, wilayah lewat
  `region_code` + `valid_from`. Kedua database diisi seed masing-masing, jadi
  UUID-nya berbeda; yang harus sama adalah isinya. Referensi yang tidak ada di
  produksi membuat promosi ditolak seluruhnya.
- Versi dataset disalin dengan UUID yang sama, supaya satu versi bisa dilacak
  di kedua database.
- Versi baru sebuah dataset menggantikan baris versi lama dataset yang sama.
  Versi lama tetap tercatat di `dataset_versions` sebagai riwayat.
- Bila baris yang akan masuk bertabrakan dengan baris dari dataset LAIN
  (misalnya data resmi dan data Sirekap untuk kecamatan yang sama), promosi
  ditolak. Pilihan mana yang dipakai adalah keputusan manusia, bukan urutan
  impor.
- Promosi ke produksi berjalan dalam satu transaksi milik pemanggil: semua
  atau tidak sama sekali.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import cast

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import (
    ITEM_COLUMN,
    MODEL_BY_KIND,
    DatasetError,
    ResultRow,
    VersionScope,
    check_conflicts,
    delete_rows,
    describe,
    replacement_warnings,
    version_scope,
)
from app.importer.format import RecordKind
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
)
from app.models.enums import JobStatus, ValidationStatus

# Berapa contoh yang disebut di pesan galat.
MAX_EXAMPLES = 10

# Kolom angka yang disalin apa adanya.
VALUE_COLUMNS: dict[RecordKind, tuple[str, ...]] = {
    RecordKind.PARTY_VOTES: ("vote_count",),
    RecordKind.CANDIDATE_VOTES: ("vote_count",),
    RecordKind.TURNOUT: ("registered_voters", "voters_turned_out", "valid_votes", "invalid_votes"),
}


@dataclass
class PromotionReport:
    version_id: uuid.UUID
    dataset_name: str
    version_number: int
    scope: str
    inserted: int = 0
    replaced: int = 0
    replaced_versions: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _examples(items: Sequence[object]) -> str:
    shown = ", ".join(map(str, list(items)[:MAX_EXAMPLES]))
    if len(items) > MAX_EXAMPLES:
        shown += f", dan {len(items) - MAX_EXAMPLES} lainnya"
    return shown


# --------------------------------------------------------------------------- #
# Pemetaan referensi staging -> produksi
# --------------------------------------------------------------------------- #


async def _production_source(
    production: AsyncSession, source: DataSource
) -> tuple[DataSource, bool]:
    """Sumber yang sepadan di produksi, dan apakah ia baru (belum ditambahkan)."""
    existing = await production.scalar(
        select(DataSource).where(DataSource.source_name == source.source_name)
    )
    fields = ("source_type", "source_url", "collection_method", "retrieved_at", "checksum_sha256")
    if existing is None:
        copy = DataSource(
            id=source.id,
            source_name=source.source_name,
            notes=source.notes,
            **{name: getattr(source, name) for name in fields},
        )
        return copy, True
    different = [name for name in fields if getattr(existing, name) != getattr(source, name)]
    if different:
        raise DatasetError(
            [
                f"sumber {source.source_name!r} di produksi berbeda dengan di staging "
                f"({', '.join(different)}); samakan dulu, asal-usul tidak boleh berubah diam-diam"
            ]
        )
    return existing, False


async def _production_election(production: AsyncSession, election: Election) -> Election:
    found = await production.scalar(
        select(Election).where(
            Election.election_type == election.election_type,
            Election.election_year == election.election_year,
        )
    )
    if found is None:
        raise DatasetError(
            [
                f"kontestasi {election.election_type.value} {election.election_year} belum ada "
                "di produksi; jalankan seed data referensi di produksi"
            ]
        )
    return found


async def _map_regions(
    staging: AsyncSession,
    production: AsyncSession,
    ids: set[uuid.UUID],
    election: Election,
    errors: list[str],
) -> dict[uuid.UUID, uuid.UUID]:
    """Wilayah staging -> wilayah produksi dengan kode dan valid_from yang sama.

    Wilayah produksi juga harus berlaku pada hari pemungutan suara kontestasi
    itu: valid_until di produksi bisa saja berbeda dengan di staging.
    """
    keys = {
        region_id: (code, valid_from)
        for region_id, code, valid_from in (
            await staging.execute(
                select(Region.id, Region.region_code, Region.valid_from).where(Region.id.in_(ids))
            )
        )
        .tuples()
        .all()
    }
    day = election.election_date
    found: dict[tuple[str, date], uuid.UUID] = {}
    expired: list[str] = []
    for region_id, code, valid_from, valid_until in (
        await production.execute(
            select(Region.id, Region.region_code, Region.valid_from, Region.valid_until).where(
                tuple_(Region.region_code, Region.valid_from).in_(list(keys.values()))
            )
        )
    ).tuples():
        if day is not None and (valid_from > day or (valid_until and valid_until < day)):
            expired.append(f"{code} (berlaku {valid_from} s.d. {valid_until})")
            continue
        found[(code, valid_from)] = region_id
    missing = sorted(
        f"{code} (berlaku {valid_from})"
        for code, valid_from in keys.values()
        if (code, valid_from) not in found and not any(e.startswith(f"{code} ") for e in expired)
    )
    if missing:
        errors.append(
            f"{len(missing)} wilayah belum ada di produksi: {_examples(missing)}; "
            "impor wilayah ke produksi lebih dulu"
        )
    if expired:
        errors.append(
            f"{len(expired)} wilayah di produksi tidak berlaku pada hari pemungutan suara "
            f"{day}: {_examples(sorted(expired))}; samakan masa berlakunya dengan staging"
        )
    return {sid: found[key] for sid, key in keys.items() if key in found}


async def _map_parties(
    staging: AsyncSession, production: AsyncSession, ids: set[uuid.UUID], errors: list[str]
) -> dict[uuid.UUID, uuid.UUID]:
    codes = dict(
        (await staging.execute(select(Party.id, Party.party_code).where(Party.id.in_(ids))))
        .tuples()
        .all()
    )
    found = dict(
        (
            await production.execute(
                select(Party.party_code, Party.id).where(Party.party_code.in_(codes.values()))
            )
        )
        .tuples()
        .all()
    )
    missing = sorted(code for code in codes.values() if code not in found)
    if missing:
        errors.append(f"partai belum ada di produksi: {_examples(missing)}")
    return {sid: found[code] for sid, code in codes.items() if code in found}


async def _map_pairs(
    staging: AsyncSession,
    production: AsyncSession,
    ids: set[uuid.UUID],
    election: Election,
    errors: list[str],
) -> dict[uuid.UUID, uuid.UUID]:
    numbers = dict(
        (
            await staging.execute(
                select(CandidatePair.id, CandidatePair.pair_number).where(CandidatePair.id.in_(ids))
            )
        )
        .tuples()
        .all()
    )
    found = dict(
        (
            await production.execute(
                select(CandidatePair.pair_number, CandidatePair.id).where(
                    CandidatePair.election_id == election.id
                )
            )
        )
        .tuples()
        .all()
    )
    missing = sorted(n for n in numbers.values() if n not in found)
    if missing:
        errors.append(
            f"paslon Pilpres {election.election_year} belum ada di produksi: "
            f"nomor {_examples(missing)}"
        )
    return {sid: found[n] for sid, n in numbers.items() if n in found}


# --------------------------------------------------------------------------- #
# Promosi
# --------------------------------------------------------------------------- #


async def _check_promotable(
    staging: AsyncSession, production: AsyncSession, version_id: uuid.UUID
) -> tuple[DatasetVersion, VersionScope, list[DatasetVersion]]:
    version = await staging.get(DatasetVersion, version_id)
    if version is None:
        raise DatasetError([f"versi dataset {version_id} tidak ada di staging"])
    label = f"{version.dataset_name} v{version.version_number}"
    if version.validation_status is ValidationStatus.PENDING:
        raise DatasetError(
            [
                f"{label} belum direkonsiliasi (T3.3); promosi ditahan sampai rekonsiliasi "
                "terhadap rekapitulasi resmi lolos"
            ]
        )
    if version.validation_status is not ValidationStatus.PASSED:
        raise DatasetError(
            [
                f"{label} berstatus {version.validation_status.value}; "
                "hanya versi passed yang boleh dipromosikan"
            ]
        )
    if await production.get(DatasetVersion, version_id) is not None:
        raise DatasetError([f"{label} sudah dipromosikan ke produksi"])

    earlier = list(
        (
            await production.scalars(
                select(DatasetVersion).where(DatasetVersion.dataset_name == version.dataset_name)
            )
        ).all()
    )
    newer = sorted(v.version_number for v in earlier if v.version_number >= version.version_number)
    if newer:
        raise DatasetError(
            [
                f"produksi sudah memuat {version.dataset_name} v{newer[-1]}; "
                f"v{version.version_number} lebih lama dan tidak boleh menimpanya"
            ]
        )
    scope = await version_scope(staging, version_id)
    if scope is None:
        raise DatasetError(
            [
                f"{label} tidak punya baris hasil di staging; "
                "kemungkinan sudah digantikan versi yang lebih baru"
            ]
        )

    return version, scope, earlier


async def promote_version(
    staging: AsyncSession, production: AsyncSession, version_id: uuid.UUID
) -> PromotionReport:
    """Salin satu versi ke produksi. Tidak melakukan commit di kedua sesi."""
    started = datetime.now(UTC)
    version, scope, earlier = await _check_promotable(staging, production, version_id)
    kind = scope.kind
    model = MODEL_BY_KIND[kind]
    report = PromotionReport(
        version.id, version.dataset_name, version.version_number, describe(scope)
    )

    staged_rows = cast(
        Sequence[ResultRow],
        (await staging.scalars(select(model).where(model.dataset_version_id == version.id))).all(),
    )

    staging_source = await staging.get(DataSource, version.source_id)
    assert staging_source is not None  # dijamin foreign key
    source, source_is_new = await _production_source(production, staging_source)
    election = await _production_election(production, scope.election)

    errors: list[str] = []
    regions = await _map_regions(
        staging, production, {r.region_id for r in staged_rows}, election, errors
    )
    items: dict[uuid.UUID, uuid.UUID] = {}
    if kind is RecordKind.PARTY_VOTES:
        items = await _map_parties(
            staging,
            production,
            {r.party_id for r in staged_rows if isinstance(r, ElectionResult)},
            errors,
        )
    elif kind is RecordKind.CANDIDATE_VOTES:
        items = await _map_pairs(
            staging,
            production,
            {r.candidate_pair_id for r in staged_rows if isinstance(r, CandidateResult)},
            election,
            errors,
        )
    if errors:
        raise DatasetError(errors)

    item_column = ITEM_COLUMN[kind]
    new_rows: list[ResultRow] = []
    for staged in staged_rows:
        values: dict[str, object] = {
            "election_id": election.id,
            "region_id": regions[staged.region_id],
            "source_id": source.id,
            "dataset_version_id": version.id,
            "data_status": staged.data_status,
            **{name: getattr(staged, name) for name in VALUE_COLUMNS[kind]},
        }
        if item_column is not None:
            values[item_column] = items[getattr(staged, item_column)]
        new_rows.append(model(**values))

    # Semua pemeriksaan selesai sebelum satu baris pun ditulis.
    earlier_ids = [v.id for v in earlier]
    report.warnings = await replacement_warnings(
        production, kind, earlier, new_rows, version.data_status, where="produksi"
    )
    await check_conflicts(
        production, kind, election.id, new_rows, where="produksi", ignore_versions=earlier_ids
    )

    if source_is_new:
        production.add(source)
    if earlier_ids:
        # Ganti baris versi lama dataset yang sama.
        report.replaced = await delete_rows(production, kind, earlier_ids)
        report.replaced_versions = sorted(v.version_number for v in earlier)
    production.add(
        DatasetVersion(
            id=version.id,
            source_id=source.id,
            dataset_name=version.dataset_name,
            version_number=version.version_number,
            collected_at=version.collected_at,
            record_count=version.record_count,
            validation_status=version.validation_status,
            data_status=version.data_status,
            file_reference=version.file_reference,
            notes=version.notes,
        )
    )
    await production.flush()
    production.add_all(new_rows)
    report.inserted = len(new_rows)

    payload: dict[str, object] = {
        "dataset_name": version.dataset_name,
        "version_number": version.version_number,
        "scope": report.scope,
        "inserted": report.inserted,
        "replaced": report.replaced,
        "replaced_versions": report.replaced_versions,
        "replacement_warnings": report.warnings,
    }
    production.add(
        IngestionJob(
            job_type="promote",
            status=JobStatus.SUCCEEDED,
            source_id=source.id,
            dataset_version_id=version.id,
            started_at=started,
            finished_at=datetime.now(UTC),
            record_count=report.inserted,
        )
    )
    production.add(
        AuditLog(
            action="dataset.promote",
            entity_type="dataset_versions",
            entity_id=version.id,
            payload=payload,
        )
    )
    await production.flush()
    return report


def promotion_audit(report: PromotionReport) -> AuditLog:
    """Catatan untuk staging, ditulis setelah produksi berhasil di-commit."""
    return AuditLog(
        action="dataset.promoted",
        entity_type="dataset_versions",
        entity_id=report.version_id,
        payload={
            "dataset_name": report.dataset_name,
            "version_number": report.version_number,
            "inserted": report.inserted,
            "replaced": report.replaced,
        },
    )
