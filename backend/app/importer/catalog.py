"""Katalog referensi untuk validator impor: apa yang sah dirujuk oleh berkas impor.

Validator sendiri murni dan hanya menerima katalog ini, supaya bisa diuji tanpa
database. `load_catalog` membangunnya dari database.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CandidatePair, Election, Party, Region
from app.models.enums import ElectionType
from app.seed.reference import SUPPORTED_YEARS

ElectionKey = tuple[ElectionType, int]


@dataclass(frozen=True)
class ReferenceCatalog:
    # Kontestasi yang ada di tabel elections.
    elections: frozenset[ElectionKey]
    # party_code -> tahun-tahun pemilu yang diikuti partai itu.
    party_years: Mapping[str, frozenset[int]]
    # (tahun, nomor urut) pasangan calon Pilpres.
    candidate_pairs: frozenset[tuple[int, int]]
    # kontestasi -> kode wilayah yang berlaku pada hari pemungutan suaranya.
    regions: Mapping[ElectionKey, frozenset[str]]
    # kontestasi -> kode yang punya lebih dari satu versi berlaku pada hari itu.
    # Skema hanya unik pada (region_code, valid_from), jadi masa berlaku yang
    # tumpang-tindih mungkin terjadi; baris dengan kode seperti ini ditolak.
    ambiguous_regions: Mapping[ElectionKey, frozenset[str]] = field(default_factory=dict)
    # Kontestasi tanpa tanggal pemungutan suara: wilayahnya tidak bisa ditentukan.
    undated_elections: frozenset[ElectionKey] = frozenset()


async def load_catalog(session: AsyncSession) -> ReferenceCatalog:
    elections = (await session.scalars(select(Election))).all()

    regions: dict[ElectionKey, frozenset[str]] = {}
    ambiguous: dict[ElectionKey, frozenset[str]] = {}
    undated: set[ElectionKey] = set()
    for election in elections:
        key = (election.election_type, election.election_year)
        if election.election_date is None:
            regions[key] = frozenset()
            undated.add(key)
            continue
        # valid_until dianggap inklusif: hari terakhir wilayah itu masih berlaku.
        rows = await session.execute(
            select(Region.region_code).where(
                Region.valid_from <= election.election_date,
                or_(Region.valid_until.is_(None), Region.valid_until >= election.election_date),
            )
        )
        counts = Counter(rows.scalars().all())
        regions[key] = frozenset(counts)
        ambiguous[key] = frozenset(code for code, n in counts.items() if n > 1)

    party_years: dict[str, set[int]] = defaultdict(set)
    for party in (await session.scalars(select(Party))).all():
        for year in SUPPORTED_YEARS:
            if getattr(party, f"contested_{year}"):
                party_years[party.party_code].add(year)

    pair_rows = await session.execute(
        select(Election.election_year, CandidatePair.pair_number).join(
            Election, CandidatePair.election_id == Election.id
        )
    )

    return ReferenceCatalog(
        elections=frozenset((e.election_type, e.election_year) for e in elections),
        party_years={code: frozenset(years) for code, years in party_years.items()},
        candidate_pairs=frozenset((year, number) for year, number in pair_rows.all()),
        regions=regions,
        ambiguous_regions=ambiguous,
        undated_elections=frozenset(undated),
    )
