"""Metadata sumber dan riwayat versi dataset (T5.3). Hanya membaca."""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import MODEL_BY_KIND, WITHDRAW_ACTION
from app.importer.format import RecordKind
from app.models import AuditLog, DatasetVersion, DataSource, Election, Region
from app.models.enums import RegionLevel
from app.schemas.metadata import (
    DatasetHistory,
    DatasetSummary,
    SourceDetail,
    SourceOut,
    VersionEvent,
    VersionOut,
)
from app.services.results import NotFoundError

LEVEL_ORDER = (RegionLevel.PROVINCE, RegionLevel.REGENCY, RegionLevel.DISTRICT)


def _source_out(source: DataSource, version_count: int) -> SourceOut:
    return SourceOut(
        id=source.id,
        name=source.source_name,
        type=source.source_type,
        url=source.source_url,
        collection_method=source.collection_method,
        retrieved_at=source.retrieved_at,
        checksum_sha256=source.checksum_sha256,
        notes=source.notes,
        version_count=version_count,
    )


@dataclass
class _Scope:
    kind: RecordKind
    election_id: uuid.UUID
    levels: set[RegionLevel] = field(default_factory=set)


async def _scopes(
    session: AsyncSession, version_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, _Scope]:
    """Jenis data, kontestasi, dan tingkat wilayah semua versi sekaligus.

    Satu kueri berkelompok per tabel hasil, bukan beberapa kueri per versi.
    Versi tanpa baris (digantikan atau ditarik) tidak muncul di sini.
    """
    scopes: dict[uuid.UUID, _Scope] = {}
    if not version_ids:
        return scopes
    for kind, model in MODEL_BY_KIND.items():
        rows = await session.execute(
            select(model.dataset_version_id, model.election_id, Region.region_level)
            .join(Region, model.region_id == Region.id)
            .where(model.dataset_version_id.in_(version_ids))
            .distinct()
        )
        for version_id, election_id, level in rows.tuples():
            scope = scopes.setdefault(version_id, _Scope(kind, election_id))
            scope.levels.add(level)
    return scopes


async def _versions_out(
    session: AsyncSession, versions: Sequence[DatasetVersion]
) -> list[VersionOut]:
    """Metadata semua versi dengan jumlah kueri tetap, berapa pun banyaknya versi."""
    ids = [v.id for v in versions]
    source_names = dict(
        (
            await session.execute(
                select(DataSource.id, DataSource.source_name).where(
                    DataSource.id.in_({v.source_id for v in versions})
                )
            )
        )
        .tuples()
        .all()
    )
    scopes = await _scopes(session, ids)
    elections = {
        e.id: e
        for e in (
            await session.scalars(
                select(Election).where(Election.id.in_({s.election_id for s in scopes.values()}))
            )
        ).all()
    }
    events: dict[uuid.UUID, list[AuditLog]] = defaultdict(list)
    if ids:
        for event in (
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_type == "dataset_versions", AuditLog.entity_id.in_(ids))
                .order_by(AuditLog.created_at)
            )
        ).all():
            if event.entity_id is not None:
                events[event.entity_id].append(event)
    numbers: dict[str, list[int]] = defaultdict(list)
    for v in versions:
        numbers[v.dataset_name].append(v.version_number)

    out: list[VersionOut] = []
    for v in versions:
        version_events = events.get(v.id, [])
        withdrawn = any(e.action == WITHDRAW_ACTION for e in version_events)
        item = VersionOut(
            id=v.id,
            dataset_name=v.dataset_name,
            version_number=v.version_number,
            source_id=v.source_id,
            source_name=source_names.get(v.source_id, ""),
            validation_status=v.validation_status,
            data_status=v.data_status,
            record_count=v.record_count,
            collected_at=v.collected_at,
            created_at=v.created_at,
            file_reference=v.file_reference,
            notes=v.notes,
            current=False,
            withdrawn=withdrawn,
            events=[
                VersionEvent(action=e.action, at=e.created_at, details=e.payload)
                for e in version_events
            ],
        )
        scope = scopes.get(v.id)
        if scope is not None:
            election = elections[scope.election_id]
            item.current = True
            item.record_kind = scope.kind.value
            item.election_type = election.election_type
            item.election_year = election.election_year
            item.region_levels = [level for level in LEVEL_ORDER if level in scope.levels]
        elif not withdrawn:
            later = [n for n in numbers[v.dataset_name] if n > v.version_number]
            # Tanpa baris dan tidak ditarik: barisnya digantikan versi berikutnya (T3.4).
            item.superseded_by = min(later) if later else None
        out.append(item)
    return out


async def list_sources(session: AsyncSession) -> list[SourceOut]:
    counts = dict(
        (
            await session.execute(
                select(DatasetVersion.source_id, func.count()).group_by(DatasetVersion.source_id)
            )
        )
        .tuples()
        .all()
    )
    sources = (await session.scalars(select(DataSource).order_by(DataSource.source_name))).all()
    return [_source_out(s, counts.get(s.id, 0)) for s in sources]


async def source_detail(session: AsyncSession, source_id: uuid.UUID) -> SourceDetail:
    source = await session.get(DataSource, source_id)
    if source is None:
        raise NotFoundError(f"sumber {source_id} tidak ada")
    # Riwayat lengkap dataset yang memakai sumber ini, supaya "digantikan oleh"
    # tetap benar walau versi penggantinya bersumber lain.
    names = (
        await session.scalars(
            select(DatasetVersion.dataset_name)
            .where(DatasetVersion.source_id == source_id)
            .distinct()
        )
    ).all()
    versions = (
        await session.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_name.in_(names))
            .order_by(DatasetVersion.dataset_name, DatasetVersion.version_number.desc())
        )
    ).all()
    out = [v for v in await _versions_out(session, versions) if v.source_id == source_id]
    return SourceDetail(source=_source_out(source, len(out)), versions=out)


async def list_datasets(session: AsyncSession) -> list[DatasetSummary]:
    versions = (
        await session.scalars(
            select(DatasetVersion).order_by(
                DatasetVersion.dataset_name, DatasetVersion.version_number.desc()
            )
        )
    ).all()
    by_name: dict[str, list[VersionOut]] = defaultdict(list)
    for v in await _versions_out(session, versions):
        by_name[v.dataset_name].append(v)
    return [
        DatasetSummary(
            dataset_name=name,
            current=next((v for v in items if v.current), None),
            latest_version=max(v.version_number for v in items),
            version_count=len(items),
        )
        for name, items in sorted(by_name.items())
    ]


async def dataset_history(session: AsyncSession, dataset_name: str) -> DatasetHistory:
    versions = (
        await session.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_name == dataset_name)
            .order_by(DatasetVersion.version_number.desc())
        )
    ).all()
    if not versions:
        raise NotFoundError(f"dataset {dataset_name!r} tidak ada")
    return DatasetHistory(
        dataset_name=dataset_name, versions=await _versions_out(session, versions)
    )
