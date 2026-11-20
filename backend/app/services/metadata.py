"""Metadata sumber dan riwayat versi dataset (T5.3). Hanya membaca."""

import uuid
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.common import MODEL_BY_KIND, version_scope
from app.models import AuditLog, DatasetVersion, DataSource, Region
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


async def _version_out(
    session: AsyncSession,
    version: DatasetVersion,
    source_name: str,
    later_numbers: Sequence[int],
) -> VersionOut:
    out = VersionOut(
        id=version.id,
        dataset_name=version.dataset_name,
        version_number=version.version_number,
        source_id=version.source_id,
        source_name=source_name,
        validation_status=version.validation_status,
        data_status=version.data_status,
        record_count=version.record_count,
        collected_at=version.collected_at,
        created_at=version.created_at,
        file_reference=version.file_reference,
        notes=version.notes,
        current=False,
    )

    scope = await version_scope(session, version.id)
    if scope is not None:
        model = MODEL_BY_KIND[scope.kind]
        levels = set(
            (
                await session.scalars(
                    select(Region.region_level)
                    .join(model, model.region_id == Region.id)
                    .where(model.dataset_version_id == version.id)
                    .distinct()
                )
            ).all()
        )
        out.current = True
        out.record_kind = scope.kind.value
        out.election_type = scope.election.election_type
        out.election_year = scope.election.election_year
        out.region_levels = [level for level in LEVEL_ORDER if level in levels]
    elif later_numbers:
        # Tanpa baris: barisnya sudah digantikan versi berikutnya (T3.4).
        out.superseded_by = min(later_numbers)

    events = (
        await session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "dataset_versions", AuditLog.entity_id == version.id)
            .order_by(AuditLog.created_at)
        )
    ).all()
    out.events = [VersionEvent(action=e.action, at=e.created_at, details=e.payload) for e in events]
    return out


async def _versions_out(
    session: AsyncSession, versions: Sequence[DatasetVersion]
) -> list[VersionOut]:
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
    numbers: dict[str, list[int]] = defaultdict(list)
    for v in versions:
        numbers[v.dataset_name].append(v.version_number)
    return [
        await _version_out(
            session,
            v,
            source_names.get(v.source_id, ""),
            [n for n in numbers[v.dataset_name] if n > v.version_number],
        )
        for v in versions
    ]


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
