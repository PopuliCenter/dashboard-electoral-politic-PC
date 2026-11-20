"""Pembantu bersama untuk muat-staging dan promosi."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importer.format import RecordKind
from app.models import CandidateResult, DatasetVersion, Election, ElectionResult, RegionTurnout

ResultRow = ElectionResult | CandidateResult | RegionTurnout
ResultModel = type[ElectionResult] | type[CandidateResult] | type[RegionTurnout]

MODEL_BY_KIND: dict[RecordKind, ResultModel] = {
    RecordKind.PARTY_VOTES: ElectionResult,
    RecordKind.CANDIDATE_VOTES: CandidateResult,
    RecordKind.TURNOUT: RegionTurnout,
}

# Kolom kunci baris hasil selain election_id dan region_id (lihat UniqueConstraint
# di app/models/result.py).
ITEM_COLUMN: dict[RecordKind, str | None] = {
    RecordKind.PARTY_VOTES: "party_id",
    RecordKind.CANDIDATE_VOTES: "candidate_pair_id",
    RecordKind.TURNOUT: None,
}


class DatasetError(Exception):
    """Muat atau promosi ditolak. `errors` berisi semua alasannya."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        daftar = "\n".join(f"  - {error}" for error in errors)
        super().__init__(f"{len(errors)} masalah:\n{daftar}")


@dataclass(frozen=True)
class VersionScope:
    """Isi satu versi dataset: jenis data dan kontestasinya."""

    kind: RecordKind
    election: Election


async def version_scope(session: AsyncSession, version_id: uuid.UUID) -> VersionScope | None:
    """Jenis data dan kontestasi sebuah versi, dibaca dari barisnya.

    None bila versi itu tidak punya baris (misalnya gagal validasi). Satu versi
    selalu berasal dari satu berkas impor, jadi hanya ada satu jenis dan satu
    kontestasi; tidak perlu kolom tambahan di `dataset_versions`.
    """
    for kind, model in MODEL_BY_KIND.items():
        election_id = await session.scalar(
            select(model.election_id).where(model.dataset_version_id == version_id).limit(1)
        )
        if election_id is not None:
            election = await session.get(Election, election_id)
            assert election is not None  # dijamin foreign key
            return VersionScope(kind, election)
    return None


def describe(scope: VersionScope) -> str:
    election = scope.election
    return f"{scope.kind.value} {election.election_type.value} {election.election_year}"


def row_key(kind: RecordKind, row: ResultRow) -> tuple[uuid.UUID, ...]:
    item = ITEM_COLUMN[kind]
    return (row.region_id,) if item is None else (row.region_id, getattr(row, item))


async def delete_rows(session: AsyncSession, kind: RecordKind, version_ids: list[uuid.UUID]) -> int:
    """Hapus baris hasil milik versi-versi tertentu. Kembalikan jumlahnya."""
    model = MODEL_BY_KIND[kind]
    result = await session.execute(delete(model).where(model.dataset_version_id.in_(version_ids)))
    return int(getattr(result, "rowcount", 0) or 0)


async def check_conflicts(
    session: AsyncSession,
    kind: RecordKind,
    election_id: uuid.UUID,
    rows: Sequence[ResultRow],
    *,
    where: str,
    ignore_versions: Sequence[uuid.UUID] = (),
) -> None:
    """Tolak bila baris baru menabrak baris milik dataset lain.

    Satu sel (kontestasi x wilayah x partai/paslon) hanya boleh punya satu angka.
    Bila dua dataset mengklaim sel yang sama (misalnya data resmi dan Sirekap),
    pilihan mana yang dipakai adalah keputusan manusia, bukan urutan impor.
    """
    model = MODEL_BY_KIND[kind]
    new_keys = {row_key(kind, row) for row in rows}
    region_ids = {row.region_id for row in rows}
    existing = cast(
        Sequence[ResultRow],
        (
            await session.scalars(
                select(model).where(
                    model.election_id == election_id, model.region_id.in_(region_ids)
                )
            )
        ).all(),
    )
    clashes: dict[uuid.UUID, int] = {}
    for row in existing:
        if row.dataset_version_id in ignore_versions:
            continue
        if row_key(kind, row) in new_keys:
            clashes[row.dataset_version_id] = clashes.get(row.dataset_version_id, 0) + 1
    if not clashes:
        return
    owners = (
        await session.scalars(select(DatasetVersion).where(DatasetVersion.id.in_(clashes)))
    ).all()
    raise DatasetError(
        [
            f"{clashes[v.id]} baris bertabrakan dengan dataset {v.dataset_name} "
            f"v{v.version_number} ({v.data_status.value}) yang sudah ada di {where}; "
            "putuskan mana yang dipakai, lalu tarik yang lain lebih dulu"
            for v in owners
        ]
    )
