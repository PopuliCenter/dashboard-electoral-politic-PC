"""Laporan kelengkapan per kontestasi dan tingkat wilayah (T3.5).

Kelengkapan dilaporkan terpisah dari akurasi (REVISI-v1.1 bagian 3): laporan
ini hanya menghitung angka apa yang ADA, tidak menilai benar-salahnya (itu
rekonsiliasi T3.3) dan tidak menerapkan ambang apa pun (ambang Gerbang 1 masih
keputusan terbuka).

Definisi, per wilayah yang berlaku pada hari pemungutan suara:

- Suara lengkap: setiap partai peserta pemilu tahun itu (Pilpres: setiap paslon)
  punya angka. Sebagian: hanya sebagian yang punya. Kosong: tidak ada sama sekali.
  Angka 0 dihitung ada; yang dihitung tidak ada adalah baris yang tidak ada.
- Partisipasi: per kolom (DPT, pengguna hak pilih, suara sah, suara tidak sah),
  berapa wilayah yang punya angkanya.
- Status: berapa wilayah yang datanya resmi, tidak resmi, atau agregat internal.

Perhitungan (`summarize`) murni dan diuji tanpa database; `load_inputs`
membacanya dari database.
"""

import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CandidatePair,
    CandidateResult,
    Election,
    ElectionResult,
    Party,
    Region,
    RegionTurnout,
)
from app.models.enums import DataStatus, ElectionType, RegionLevel
from app.seed.reference import SUPPORTED_YEARS

TURNOUT_FIELDS = ("registered_voters", "voters_turned_out", "valid_votes", "invalid_votes")
LEVEL_ORDER = (RegionLevel.PROVINCE, RegionLevel.REGENCY, RegionLevel.DISTRICT)


class VoteCoverage(StrEnum):
    COMPLETE = "lengkap"
    PARTIAL = "sebagian"
    EMPTY = "kosong"


@dataclass(frozen=True)
class RegionRef:
    id: uuid.UUID
    code: str
    name: str
    level: RegionLevel


@dataclass(frozen=True)
class ElectionInputs:
    """Semua yang dibutuhkan untuk menghitung kelengkapan satu kontestasi."""

    election_type: ElectionType
    election_year: int
    regions: tuple[RegionRef, ...]
    # Kode partai peserta (legislatif) atau nomor paslon (Pilpres), sebagai teks.
    expected_items: frozenset[str]
    # wilayah -> item yang punya angka suara.
    votes: Mapping[uuid.UUID, frozenset[str]]
    # wilayah -> status data baris suara dan partisipasinya.
    statuses: Mapping[uuid.UUID, frozenset[DataStatus]]
    # wilayah -> kolom partisipasi yang terisi.
    turnout: Mapping[uuid.UUID, frozenset[str]]


@dataclass(frozen=True)
class RegionDetail:
    election_type: ElectionType
    election_year: int
    region: RegionRef
    coverage: VoteCoverage
    missing_items: tuple[str, ...]
    turnout_fields: frozenset[str]
    statuses: frozenset[DataStatus]


@dataclass
class LevelSummary:
    election_type: ElectionType
    election_year: int
    level: RegionLevel
    regions: int = 0
    coverage: Counter[VoteCoverage] = field(default_factory=Counter)
    turnout: Counter[str] = field(default_factory=Counter)
    statuses: Counter[DataStatus] = field(default_factory=Counter)
    # Wilayah yang datanya bercampur resmi dan tidak resmi.
    mixed_status: int = 0

    def percent(self, count: int) -> float | None:
        return None if self.regions == 0 else count / self.regions * 100


@dataclass
class CompletenessReport:
    summaries: list[LevelSummary]
    details: list[RegionDetail]
    # Peringatan tentang referensi yang kosong, supaya 0% tidak disalahpahami.
    warnings: list[str] = field(default_factory=list)


def _label(election_type: ElectionType, year: int) -> str:
    return f"{election_type.value} {year}"


def summarize(inputs: Iterable[ElectionInputs]) -> CompletenessReport:
    report = CompletenessReport([], [])
    for data in inputs:
        label = _label(data.election_type, data.election_year)
        if not data.regions:
            report.warnings.append(
                f"{label}: tidak ada wilayah yang berlaku pada hari pemungutan suara; "
                "impor wilayah (T2.2) dulu"
            )
        if not data.expected_items:
            report.warnings.append(
                f"{label}: daftar partai/paslon peserta kosong; jalankan seed (T2.5) dulu"
            )

        by_level: dict[RegionLevel, LevelSummary] = {}
        for region in sorted(data.regions, key=lambda r: (LEVEL_ORDER.index(r.level), r.code)):
            summary = by_level.setdefault(
                region.level, LevelSummary(data.election_type, data.election_year, region.level)
            )
            present = data.votes.get(region.id, frozenset()) & data.expected_items
            if not present:
                coverage = VoteCoverage.EMPTY
            elif present == data.expected_items:
                coverage = VoteCoverage.COMPLETE
            else:
                coverage = VoteCoverage.PARTIAL
            fields = data.turnout.get(region.id, frozenset())
            statuses = data.statuses.get(region.id, frozenset())

            summary.regions += 1
            summary.coverage[coverage] += 1
            summary.turnout.update(fields)
            summary.statuses.update(statuses)
            if len(statuses) > 1:
                summary.mixed_status += 1
            report.details.append(
                RegionDetail(
                    data.election_type,
                    data.election_year,
                    region,
                    coverage,
                    tuple(sorted(data.expected_items - present, key=_item_sort)),
                    fields,
                    statuses,
                )
            )
        report.summaries.extend(by_level[level] for level in LEVEL_ORDER if level in by_level)
    return report


def _item_sort(item: str) -> tuple[int, str]:
    # Nomor paslon diurutkan sebagai angka, kode partai sebagai teks.
    return (int(item), "") if item.isdigit() else (0, item)


# --------------------------------------------------------------------------- #
# Membaca dari database
# --------------------------------------------------------------------------- #


async def load_inputs(
    session: AsyncSession, elections: Iterable[tuple[ElectionType, int]] | None = None
) -> list[ElectionInputs]:
    """Siapkan masukan untuk kontestasi yang diminta (bawaan: semua di fase 1)."""
    wanted = set(elections) if elections is not None else None
    rows = (
        await session.scalars(
            select(Election)
            .where(Election.election_year.in_(SUPPORTED_YEARS))
            .order_by(Election.election_year, Election.election_type)
        )
    ).all()

    inputs: list[ElectionInputs] = []
    for election in rows:
        if wanted is not None and (election.election_type, election.election_year) not in wanted:
            continue
        inputs.append(await _load_one(session, election))
    return inputs


async def _load_one(session: AsyncSession, election: Election) -> ElectionInputs:
    regions: tuple[RegionRef, ...] = ()
    if election.election_date is not None:
        regions = tuple(
            RegionRef(rid, code, name, level)
            for rid, code, name, level in (
                await session.execute(
                    select(
                        Region.id, Region.region_code, Region.region_name, Region.region_level
                    ).where(
                        Region.valid_from <= election.election_date,
                        or_(
                            Region.valid_until.is_(None),
                            Region.valid_until >= election.election_date,
                        ),
                    )
                )
            )
            .tuples()
            .all()
        )

    votes: dict[uuid.UUID, set[str]] = {}
    statuses: dict[uuid.UUID, set[DataStatus]] = {}

    if election.election_type is ElectionType.PRESIDENTIAL:
        expected = frozenset(
            str(n)
            for n in (
                await session.scalars(
                    select(CandidatePair.pair_number).where(
                        CandidatePair.election_id == election.id
                    )
                )
            ).all()
        )
        vote_rows = (
            await session.execute(
                select(
                    CandidateResult.region_id,
                    CandidatePair.pair_number,
                    CandidateResult.data_status,
                )
                .join(CandidatePair, CandidateResult.candidate_pair_id == CandidatePair.id)
                .where(CandidateResult.election_id == election.id)
            )
        ).tuples()
        for region_id, number, status in vote_rows:
            votes.setdefault(region_id, set()).add(str(number))
            statuses.setdefault(region_id, set()).add(status)
    else:
        contested = getattr(Party, f"contested_{election.election_year}")
        expected = frozenset(
            (await session.scalars(select(Party.party_code).where(contested.is_(True)))).all()
        )
        vote_rows_party = (
            await session.execute(
                select(ElectionResult.region_id, Party.party_code, ElectionResult.data_status)
                .join(Party, ElectionResult.party_id == Party.id)
                .where(ElectionResult.election_id == election.id)
            )
        ).tuples()
        for region_id, code, status in vote_rows_party:
            votes.setdefault(region_id, set()).add(code)
            statuses.setdefault(region_id, set()).add(status)

    turnout: dict[uuid.UUID, frozenset[str]] = {}
    for row in (
        await session.scalars(select(RegionTurnout).where(RegionTurnout.election_id == election.id))
    ).all():
        turnout[row.region_id] = frozenset(
            name for name in TURNOUT_FIELDS if getattr(row, name) is not None
        )
        statuses.setdefault(row.region_id, set()).add(row.data_status)

    return ElectionInputs(
        election_type=election.election_type,
        election_year=election.election_year,
        regions=regions,
        expected_items=expected,
        votes={k: frozenset(v) for k, v in votes.items()},
        statuses={k: frozenset(v) for k, v in statuses.items()},
        turnout=turnout,
    )
