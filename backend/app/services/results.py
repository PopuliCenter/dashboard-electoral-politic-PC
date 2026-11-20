"""Menyusun hasil pemilu untuk API (T4.1) dari database dan formula T4.2.

Semua kueri di sini terikat pada SATU kontestasi (aturan data 3). Wilayah yang
dipakai adalah wilayah yang berlaku pada hari pemungutan suara kontestasi itu.
"""

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CandidatePair,
    CandidateResult,
    DataSource,
    Election,
    ElectionResult,
    Party,
    Region,
    RegionCrosswalk,
    RegionTurnout,
)
from app.models.enums import DataStatus, ElectionType, RegionLevel
from app.schemas.electoral import (
    CompareOut,
    ElectionOut,
    ElectionResultsOut,
    ItemResult,
    Leader,
    PartyElectionResults,
    PartyOut,
    PartyRegionResult,
    PartyResultsOut,
    Percentage,
    RegionOut,
    RegionResult,
    Source,
    SwingUnit,
    Turnout,
)
from app.services.analytics import (
    AreaVotes,
    InconsistentDataError,
    MatchedUnit,
    SwingInput,
    Unavailable,
    aggregate,
    derive_parent_units,
    matched_units,
    party_swing,
    rank,
    restrict_units,
    turnout,
    vote_share,
    weakest_status,
)

logger = logging.getLogger(__name__)


class NotFoundError(LookupError):
    """Kontestasi, partai, atau wilayah yang diminta tidak ada."""


# --------------------------------------------------------------------------- #
# Konversi model -> skema
# --------------------------------------------------------------------------- #


def region_out(region: Region) -> RegionOut:
    return RegionOut(
        id=region.id,
        code=region.region_code,
        name=region.region_name,
        level=region.region_level,
        parent_id=region.parent_id,
        valid_from=region.valid_from,
        valid_until=region.valid_until,
    )


def election_out(election: Election) -> ElectionOut:
    return ElectionOut(
        id=election.id,
        type=election.election_type,
        year=election.election_year,
        date=election.election_date,
        name=election.election_name,
    )


def party_out(party: Party) -> PartyOut:
    return PartyOut(
        id=party.id,
        code=party.party_code,
        name=party.party_name,
        abbreviation=party.party_abbreviation,
        contested_2019=party.contested_2019,
        contested_2024=party.contested_2024,
        ballot_number_2019=party.ballot_number_2019,
        ballot_number_2024=party.ballot_number_2024,
        new_in_2024=party.contested_2024 and not party.contested_2019,
    )


def _as_percentage(value: float | Unavailable, status: DataStatus | None = None) -> Percentage:
    if isinstance(value, Unavailable):
        return Percentage(value=None, unavailable=value.value)
    return Percentage(value=value, data_status=status)


def _inconsistent(context: str, exc: InconsistentDataError) -> Percentage:
    """Data mustahil: angkanya tidak ditampilkan dan dicatat, bukan galat 500."""
    logger.warning("data tidak konsisten (%s): %s", context, exc)
    return Percentage(value=None, unavailable=Unavailable.INCONSISTENT.value)


def _share(
    votes: int | None,
    valid_votes: int | None,
    statuses: Iterable[DataStatus | None],
    context: str,
) -> Percentage:
    """Vote share dengan status terlemah dari pembilang dan penyebutnya."""
    try:
        return _as_percentage(vote_share(votes, valid_votes), weakest_status(statuses))
    except InconsistentDataError as exc:
        return _inconsistent(context, exc)


def _turnout_pct(row: RegionTurnout, context: str) -> Percentage:
    try:
        value = turnout(row.voters_turned_out, row.registered_voters)
        return _as_percentage(value, row.data_status)
    except InconsistentDataError as exc:
        return _inconsistent(context, exc)


async def _sources(session: AsyncSession, ids: Iterable[uuid.UUID | None]) -> list[Source]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return []
    rows = (await session.scalars(select(DataSource).where(DataSource.id.in_(wanted)))).all()
    return [
        Source(id=s.id, name=s.source_name, type=s.source_type, url=s.source_url)
        for s in sorted(rows, key=lambda s: s.source_name)
    ]


# --------------------------------------------------------------------------- #
# Wilayah
# --------------------------------------------------------------------------- #

# Tingkat induk langsung untuk drill-down.
PARENT_LEVEL = {
    RegionLevel.REGENCY: RegionLevel.PROVINCE,
    RegionLevel.DISTRICT: RegionLevel.REGENCY,
}


def _valid_on(election: Election) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    day = election.election_date
    return (
        Region.valid_from <= day,
        or_(Region.valid_until.is_(None), Region.valid_until >= day),
    )


def require_dated(election: Election) -> None:
    if election.election_date is None:
        raise ValueError(
            f"kontestasi {election.election_type.value} {election.election_year} belum punya "
            "tanggal pemungutan suara, jadi wilayah yang berlaku tidak bisa ditentukan"
        )


async def regions_for(
    session: AsyncSession,
    election: Election,
    level: RegionLevel,
    parent_id: uuid.UUID | None = None,
) -> list[Region]:
    require_dated(election)
    query = select(Region).where(Region.region_level == level, *_valid_on(election))
    if parent_id is not None:
        query = query.where(Region.parent_id == parent_id)
    return list((await session.scalars(query.order_by(Region.region_code))).all())


async def get_election(session: AsyncSession, election_id: uuid.UUID) -> Election:
    election = await session.get(Election, election_id)
    if election is None:
        raise NotFoundError(f"kontestasi {election_id} tidak ada")
    return election


async def _check_parent(session: AsyncSession, parent_id: uuid.UUID, level: RegionLevel) -> None:
    parent = await session.get(Region, parent_id)
    if parent is None:
        raise NotFoundError(f"wilayah induk {parent_id} tidak ada")
    expected = PARENT_LEVEL.get(level)
    if parent.region_level is not expected:
        raise ValueError(
            f"wilayah {parent.region_code} bertingkat {parent.region_level.value}, bukan induk "
            f"langsung tingkat {level.value}"
        )


# --------------------------------------------------------------------------- #
# Hasil satu kontestasi
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Vote:
    count: int
    status: DataStatus
    source_id: uuid.UUID


async def _participants(session: AsyncSession, election: Election) -> dict[str, str]:
    """Peserta kontestasi: kunci -> label, berurutan menurut nomor urut."""
    if election.election_type is ElectionType.PRESIDENTIAL:
        pairs = (
            await session.scalars(
                select(CandidatePair)
                .where(CandidatePair.election_id == election.id)
                .order_by(CandidatePair.pair_number)
            )
        ).all()
        return {
            str(p.pair_number): f"{p.pair_number}. {p.president_name} - {p.vice_president_name}"
            for p in pairs
        }
    ballot = getattr(Party, f"ballot_number_{election.election_year}", None)
    contested = getattr(Party, f"contested_{election.election_year}", None)
    if ballot is None or contested is None:
        return {}
    parties = (
        await session.scalars(select(Party).where(contested.is_(True)).order_by(ballot))
    ).all()
    return {p.party_code: p.party_abbreviation or p.party_name for p in parties}


async def _votes(
    session: AsyncSession,
    election: Election,
    region_ids: list[uuid.UUID],
    party_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, dict[str, _Vote]]:
    """Suara per wilayah per peserta. `party_id` membatasi ke satu partai."""
    votes: dict[uuid.UUID, dict[str, _Vote]] = {}
    if not region_ids:
        return votes
    if election.election_type is ElectionType.PRESIDENTIAL:
        rows = await session.execute(
            select(
                CandidateResult.region_id,
                CandidatePair.pair_number,
                CandidateResult.vote_count,
                CandidateResult.data_status,
                CandidateResult.source_id,
            )
            .join(CandidatePair, CandidateResult.candidate_pair_id == CandidatePair.id)
            .where(
                CandidateResult.election_id == election.id,
                CandidateResult.region_id.in_(region_ids),
            )
        )
        for region_id, number, count, status, source in rows.tuples():
            votes.setdefault(region_id, {})[str(number)] = _Vote(count, status, source)
        return votes
    query = (
        select(
            ElectionResult.region_id,
            Party.party_code,
            ElectionResult.vote_count,
            ElectionResult.data_status,
            ElectionResult.source_id,
        )
        .join(Party, ElectionResult.party_id == Party.id)
        .where(ElectionResult.election_id == election.id, ElectionResult.region_id.in_(region_ids))
    )
    if party_id is not None:
        query = query.where(ElectionResult.party_id == party_id)
    for region_id, code, count, status, source in (await session.execute(query)).tuples():
        votes.setdefault(region_id, {})[code] = _Vote(count, status, source)
    return votes


async def _turnouts(
    session: AsyncSession, election: Election, region_ids: list[uuid.UUID]
) -> dict[uuid.UUID, RegionTurnout]:
    if not region_ids:
        return {}
    rows = (
        await session.scalars(
            select(RegionTurnout).where(
                RegionTurnout.election_id == election.id, RegionTurnout.region_id.in_(region_ids)
            )
        )
    ).all()
    return {r.region_id: r for r in rows}


def _turnout_out(row: RegionTurnout | None, context: str) -> Turnout:
    if row is None:
        return Turnout(
            registered_voters=None,
            voters_turned_out=None,
            valid_votes=None,
            invalid_votes=None,
            turnout=Percentage(value=None, unavailable=Unavailable.NO_DATA.value),
            data_status=None,
            source_id=None,
        )
    return Turnout(
        registered_voters=row.registered_voters,
        voters_turned_out=row.voters_turned_out,
        valid_votes=row.valid_votes,
        invalid_votes=row.invalid_votes,
        turnout=_turnout_pct(row, context),
        data_status=row.data_status,
        source_id=row.source_id,
    )


def _leader(votes: dict[str, _Vote], participants: dict[str, str]) -> Leader:
    try:
        ranking = rank({k: v.count for k, v in votes.items()}, participants.keys())
    except InconsistentDataError:
        return Leader(keys=[], tie=False, margin=None, unavailable=Unavailable.INCONSISTENT.value)
    if isinstance(ranking, Unavailable):
        return Leader(keys=[], tie=False, margin=None, unavailable=ranking.value)
    return Leader(
        keys=list(ranking.leaders),
        tie=ranking.tie,
        margin=ranking.margin,
        data_status=weakest_status(v.status for k, v in votes.items() if k in participants),
    )


async def election_results(
    session: AsyncSession,
    election: Election,
    level: RegionLevel,
    parent_id: uuid.UUID | None = None,
) -> ElectionResultsOut:
    require_dated(election)
    if parent_id is not None:
        await _check_parent(session, parent_id, level)
    regions = await regions_for(session, election, level, parent_id)
    ids = [r.id for r in regions]
    participants = await _participants(session, election)
    votes = await _votes(session, election, ids)
    turnouts = await _turnouts(session, election, ids)

    out: list[RegionResult] = []
    source_ids: set[uuid.UUID] = set()
    for region in regions:
        region_votes = votes.get(region.id, {})
        turnout_row = turnouts.get(region.id)
        valid = turnout_row.valid_votes if turnout_row else None
        valid_status = turnout_row.data_status if turnout_row else None
        context = f"{election.election_type.value} {election.election_year} {region.region_code}"
        items = []
        for key, label in participants.items():
            vote = region_votes.get(key)
            items.append(
                ItemResult(
                    key=key,
                    label=label,
                    vote_count=vote.count if vote else None,
                    vote_share=_share(
                        vote.count if vote else None,
                        valid,
                        (vote.status if vote else None, valid_status),
                        f"{context} {key}",
                    ),
                    data_status=vote.status if vote else None,
                    source_id=vote.source_id if vote else None,
                )
            )
        statuses = {v.status for v in region_votes.values()}
        if turnout_row is not None:
            statuses.add(turnout_row.data_status)
            source_ids.add(turnout_row.source_id)
        source_ids.update(v.source_id for v in region_votes.values())
        out.append(
            RegionResult(
                region=region_out(region),
                results=items,
                turnout=_turnout_out(turnout_row, context),
                leader=_leader(region_votes, participants),
                data_statuses=sorted(statuses),
            )
        )
    return ElectionResultsOut(
        election=election_out(election),
        level=level,
        regions=out,
        sources=await _sources(session, source_ids),
    )


# --------------------------------------------------------------------------- #
# Perbandingan antar pemilu (swing)
# --------------------------------------------------------------------------- #


async def _election_by(session: AsyncSession, election_type: ElectionType, year: int) -> Election:
    election = await session.scalar(
        select(Election).where(
            Election.election_type == election_type, Election.election_year == year
        )
    )
    if election is None:
        raise NotFoundError(f"kontestasi {election_type.value} {year} tidak ada")
    return election


@dataclass
class _PartyArea:
    """Suara satu partai dan suara sah di satu kontestasi, per wilayah."""

    data: dict[uuid.UUID, AreaVotes]
    votes: dict[uuid.UUID, _Vote]
    statuses: dict[uuid.UUID, set[DataStatus]]
    sources: set[uuid.UUID]


async def _party_area(
    session: AsyncSession, election: Election, party: Party, regions: list[Region]
) -> _PartyArea:
    ids = [r.id for r in regions]
    votes = await _votes(session, election, ids, party_id=party.id)
    turnouts = await _turnouts(session, election, ids)
    area = _PartyArea({}, {}, {}, set())
    for region_id in ids:
        vote = votes.get(region_id, {}).get(party.party_code)
        row = turnouts.get(region_id)
        area.data[region_id] = AreaVotes(
            party_votes=vote.count if vote else None,
            valid_votes=row.valid_votes if row else None,
        )
        region_statuses = area.statuses.setdefault(region_id, set())
        if vote:
            area.votes[region_id] = vote
            region_statuses.add(vote.status)
            area.sources.add(vote.source_id)
        if row:
            region_statuses.add(row.data_status)
            area.sources.add(row.source_id)
    return area


async def _district_units(
    session: AsyncSession,
    from_year: int,
    to_year: int,
    old_regions: list[Region],
    new_regions: list[Region],
) -> tuple[list[MatchedUnit[uuid.UUID]], dict[uuid.UUID, Region]]:
    """Unit padanan tingkat kecamatan yang semua wilayahnya berlaku.

    Baris padanan dibaca utuh, termasuk yang ujungnya tidak berlaku, supaya unit
    yang menyentuh wilayah tak berlaku ikut terlihat dan ditolak seluruhnya.
    """
    old_ids = {r.id for r in old_regions}
    new_ids = {r.id for r in new_regions}
    pairs = (
        (
            await session.execute(
                select(RegionCrosswalk.from_region_id, RegionCrosswalk.to_region_id).where(
                    RegionCrosswalk.from_year == from_year,
                    RegionCrosswalk.to_year == to_year,
                    or_(
                        RegionCrosswalk.from_region_id.in_(old_ids),
                        RegionCrosswalk.to_region_id.in_(new_ids),
                    ),
                )
            )
        )
        .tuples()
        .all()
    )
    units, _broken = restrict_units(matched_units(pairs), old_ids, new_ids)
    return units, {r.id: r for r in [*old_regions, *new_regions]}


async def compare(
    session: AsyncSession,
    election_type: ElectionType,
    from_year: int,
    to_year: int,
    level: RegionLevel,
    party_id: uuid.UUID,
) -> CompareOut:
    if election_type is ElectionType.PRESIDENTIAL:
        # Paslon berbeda tiap pemilu; swing partai tidak berlaku untuk Pilpres.
        raise ValueError("perbandingan swing partai hanya untuk DPR RI dan DPRD Provinsi")
    if level not in (RegionLevel.DISTRICT, RegionLevel.REGENCY):
        raise ValueError("swing tersedia untuk tingkat kecamatan dan kab/kota")
    if from_year >= to_year:
        raise ValueError("from_year harus sebelum to_year")
    party = await session.get(Party, party_id)
    if party is None:
        raise NotFoundError(f"partai {party_id} tidak ada")
    old_election = await _election_by(session, election_type, from_year)
    new_election = await _election_by(session, election_type, to_year)

    old_districts = await regions_for(session, old_election, RegionLevel.DISTRICT)
    new_districts = await regions_for(session, new_election, RegionLevel.DISTRICT)
    district_units, by_id = await _district_units(
        session, from_year, to_year, old_districts, new_districts
    )

    if level is RegionLevel.DISTRICT:
        old_regions, new_regions, units = old_districts, new_districts, district_units
    else:
        # Unit kab/kota diturunkan dari unit kecamatan (keputusan pengguna);
        # angkanya tetap dari baris tingkat kab/kota, bukan jumlah kecamatan.
        old_regions = await regions_for(session, old_election, RegionLevel.REGENCY)
        new_regions = await regions_for(session, new_election, RegionLevel.REGENCY)
        by_id.update({r.id: r for r in [*old_regions, *new_regions]})
        old_children: dict[uuid.UUID, list[uuid.UUID]] = {r.id: [] for r in old_regions}
        new_children: dict[uuid.UUID, list[uuid.UUID]] = {r.id: [] for r in new_regions}
        for d in old_districts:
            if d.parent_id in old_children:
                old_children[d.parent_id].append(d.id)
        for d in new_districts:
            if d.parent_id in new_children:
                new_children[d.parent_id].append(d.id)
        units = derive_parent_units(district_units, old_children, new_children).units

    old = await _party_area(session, old_election, party, old_regions)
    new = await _party_area(session, new_election, party, new_regions)
    contested_old = bool(getattr(party, f"contested_{from_year}", False))
    contested_new = bool(getattr(party, f"contested_{to_year}", False))
    swing_input = SwingInput(
        election_type, election_type, contested_old, contested_new, old.data, new.data
    )

    def side_status(regions: frozenset[uuid.UUID], area: _PartyArea) -> DataStatus | None:
        return weakest_status(s for r in regions for s in area.statuses.get(r, set()))

    def side_share(regions: frozenset[uuid.UUID], area: _PartyArea) -> Percentage:
        totals = aggregate(regions, area.data)
        if isinstance(totals, Unavailable):
            return _as_percentage(totals)
        return _share(
            totals.party_votes,
            totals.valid_votes,
            [side_status(regions, area)],
            f"{party.party_code} {sorted(by_id[r].region_code for r in regions)}",
        )

    out_units: list[SwingUnit] = []
    for unit in sorted(units, key=lambda u: sorted(by_id[r].region_code for r in u.old_regions)):
        statuses = {s for r in unit.old_regions for s in old.statuses.get(r, set())} | {
            s for r in unit.new_regions for s in new.statuses.get(r, set())
        }
        # Per unit, supaya satu unit berdata mustahil tidak menjatuhkan seluruh respons.
        try:
            value = _as_percentage(party_swing(swing_input, [unit])[unit], weakest_status(statuses))
        except InconsistentDataError as exc:
            value = _inconsistent(f"swing {party.party_code}", exc)
        out_units.append(
            SwingUnit(
                old_region_codes=sorted(by_id[r].region_code for r in unit.old_regions),
                new_region_codes=sorted(by_id[r].region_code for r in unit.new_regions),
                old_share=side_share(unit.old_regions, old),
                new_share=side_share(unit.new_regions, new),
                swing=value,
                data_statuses=sorted(statuses),
            )
        )

    matched_old = {r for u in units for r in u.old_regions}
    matched_new = {r for u in units for r in u.new_regions}
    return CompareOut(
        election_type=election_type,
        from_year=from_year,
        to_year=to_year,
        level=level,
        party=party_out(party),
        units=out_units,
        unmatched_old_region_codes=sorted(
            r.region_code for r in old_regions if r.id not in matched_old
        ),
        unmatched_new_region_codes=sorted(
            r.region_code for r in new_regions if r.id not in matched_new
        ),
        sources=await _sources(session, old.sources | new.sources),
    )


# --------------------------------------------------------------------------- #
# Hasil satu partai
# --------------------------------------------------------------------------- #


async def party_results(
    session: AsyncSession,
    party_id: uuid.UUID,
    election_type: ElectionType,
    level: RegionLevel,
) -> PartyResultsOut:
    if election_type is ElectionType.PRESIDENTIAL:
        raise ValueError("hasil partai hanya untuk DPR RI dan DPRD Provinsi")
    party = await session.get(Party, party_id)
    if party is None:
        raise NotFoundError(f"partai {party_id} tidak ada")
    elections = (
        await session.scalars(
            select(Election)
            .where(Election.election_type == election_type)
            .order_by(Election.election_year)
        )
    ).all()

    out: list[PartyElectionResults] = []
    source_ids: set[uuid.UUID] = set()
    for election in elections:
        contested = bool(getattr(party, f"contested_{election.election_year}", False))
        regions = await regions_for(session, election, level)
        area = await _party_area(session, election, party, regions)
        source_ids |= area.sources
        rows: list[PartyRegionResult] = []
        for region in regions:
            vote = area.votes.get(region.id)
            numbers = area.data[region.id]
            if not contested:
                share = Percentage(value=None, unavailable=Unavailable.NOT_CONTESTED.value)
            else:
                share = _share(
                    numbers.party_votes,
                    numbers.valid_votes,
                    area.statuses.get(region.id, set()),
                    f"{party.party_code} {region.region_code}",
                )
            rows.append(
                PartyRegionResult(
                    region=region_out(region),
                    vote_count=vote.count if vote else None,
                    vote_share=share,
                    data_status=vote.status if vote else None,
                    source_id=vote.source_id if vote else None,
                )
            )
        out.append(
            PartyElectionResults(election=election_out(election), contested=contested, regions=rows)
        )
    return PartyResultsOut(
        party=party_out(party),
        level=level,
        elections=out,
        sources=await _sources(session, source_ids),
    )
