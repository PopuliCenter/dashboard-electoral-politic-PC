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
    matched_units,
    party_swing,
    rank,
    turnout,
    vote_share,
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


def _as_percentage(value: float | Unavailable) -> Percentage:
    if isinstance(value, Unavailable):
        return Percentage(value=None, unavailable=value.value)
    return Percentage(value=value)


def _inconsistent(context: str, exc: InconsistentDataError) -> Percentage:
    """Data mustahil: angkanya tidak ditampilkan dan dicatat, bukan galat 500."""
    logger.warning("data tidak konsisten (%s): %s", context, exc)
    return Percentage(value=None, unavailable=Unavailable.INCONSISTENT.value)


def _share(votes: int | None, valid_votes: int | None, context: str) -> Percentage:
    try:
        return _as_percentage(vote_share(votes, valid_votes))
    except InconsistentDataError as exc:
        return _inconsistent(context, exc)


def _turnout_pct(turned_out: int | None, registered: int | None, context: str) -> Percentage:
    try:
        return _as_percentage(turnout(turned_out, registered))
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


def _valid_on(election: Election) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    day = election.election_date
    return (
        Region.valid_from <= day,
        or_(Region.valid_until.is_(None), Region.valid_until >= day),
    )


async def regions_for(
    session: AsyncSession,
    election: Election,
    level: RegionLevel,
    parent_id: uuid.UUID | None = None,
) -> list[Region]:
    if election.election_date is None:
        return []
    query = select(Region).where(Region.region_level == level, *_valid_on(election))
    if parent_id is not None:
        query = query.where(Region.parent_id == parent_id)
    return list((await session.scalars(query.order_by(Region.region_code))).all())


async def get_election(session: AsyncSession, election_id: uuid.UUID) -> Election:
    election = await session.get(Election, election_id)
    if election is None:
        raise NotFoundError(f"kontestasi {election_id} tidak ada")
    return election


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
    session: AsyncSession, election: Election, region_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, _Vote]]:
    votes: dict[uuid.UUID, dict[str, _Vote]] = {}
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
    party_rows = await session.execute(
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
    for region_id, code, count, status, source in party_rows.tuples():
        votes.setdefault(region_id, {})[code] = _Vote(count, status, source)
    return votes


async def _turnouts(
    session: AsyncSession, election: Election, region_ids: list[uuid.UUID]
) -> dict[uuid.UUID, RegionTurnout]:
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
        turnout=_turnout_pct(row.voters_turned_out, row.registered_voters, context),
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
    return Leader(keys=list(ranking.leaders), tie=ranking.tie, margin=ranking.margin)


async def election_results(
    session: AsyncSession,
    election: Election,
    level: RegionLevel,
    parent_id: uuid.UUID | None = None,
) -> ElectionResultsOut:
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
        context = f"{election.election_type.value} {election.election_year} {region.region_code}"
        items = []
        for key, label in participants.items():
            vote = region_votes.get(key)
            items.append(
                ItemResult(
                    key=key,
                    label=label,
                    vote_count=vote.count if vote else None,
                    vote_share=_share(vote.count if vote else None, valid, f"{context} {key}"),
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


async def _party_area_votes(
    session: AsyncSession, election: Election, party: Party, regions: list[Region]
) -> tuple[dict[uuid.UUID, AreaVotes], dict[uuid.UUID, set[DataStatus]], set[uuid.UUID]]:
    ids = [r.id for r in regions]
    votes = (await _votes(session, election, ids)) if ids else {}
    turnouts = (await _turnouts(session, election, ids)) if ids else {}
    data: dict[uuid.UUID, AreaVotes] = {}
    statuses: dict[uuid.UUID, set[DataStatus]] = {}
    sources: set[uuid.UUID] = set()
    for region_id in ids:
        vote = votes.get(region_id, {}).get(party.party_code)
        row = turnouts.get(region_id)
        data[region_id] = AreaVotes(
            party_votes=vote.count if vote else None,
            valid_votes=row.valid_votes if row else None,
        )
        region_statuses = statuses.setdefault(region_id, set())
        if vote:
            region_statuses.add(vote.status)
            sources.add(vote.source_id)
        if row:
            region_statuses.add(row.data_status)
            sources.add(row.source_id)
    return data, statuses, sources


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
    if from_year >= to_year:
        raise ValueError("from_year harus sebelum to_year")
    party = await session.get(Party, party_id)
    if party is None:
        raise NotFoundError(f"partai {party_id} tidak ada")
    old_election = await _election_by(session, election_type, from_year)
    new_election = await _election_by(session, election_type, to_year)
    old_regions = await regions_for(session, old_election, level)
    new_regions = await regions_for(session, new_election, level)
    by_id = {r.id: r for r in [*old_regions, *new_regions]}

    crosswalk = (
        await session.execute(
            select(RegionCrosswalk.from_region_id, RegionCrosswalk.to_region_id).where(
                RegionCrosswalk.from_year == from_year,
                RegionCrosswalk.to_year == to_year,
                RegionCrosswalk.from_region_id.in_([r.id for r in old_regions]),
                RegionCrosswalk.to_region_id.in_([r.id for r in new_regions]),
            )
        )
    ).tuples()
    units = matched_units(crosswalk)

    old_data, old_statuses, old_sources = await _party_area_votes(
        session, old_election, party, old_regions
    )
    new_data, new_statuses, new_sources = await _party_area_votes(
        session, new_election, party, new_regions
    )
    contested_old = bool(getattr(party, f"contested_{from_year}", False))
    contested_new = bool(getattr(party, f"contested_{to_year}", False))
    swing_input = SwingInput(
        election_type, election_type, contested_old, contested_new, old_data, new_data
    )
    # Per unit, supaya satu unit berdata mustahil tidak menjatuhkan seluruh respons.
    swings: dict[MatchedUnit[uuid.UUID], Percentage] = {}
    for unit in units:
        try:
            swings[unit] = _as_percentage(party_swing(swing_input, [unit])[unit])
        except InconsistentDataError as exc:
            swings[unit] = _inconsistent(f"swing {party.party_code}", exc)

    def share(regions: frozenset[uuid.UUID], data: dict[uuid.UUID, AreaVotes]) -> Percentage:
        areas = [data.get(r) for r in regions]
        if any(a is None or a.party_votes is None or a.valid_votes is None for a in areas):
            reason = Unavailable.INCOMPLETE if len(regions) > 1 else Unavailable.NO_DATA
            return Percentage(value=None, unavailable=reason.value)
        party_total = sum(a.party_votes for a in areas if a and a.party_votes is not None)
        valid_total = sum(a.valid_votes for a in areas if a and a.valid_votes is not None)
        return _share(party_total, valid_total, party.party_code)

    out_units: list[SwingUnit] = []
    for unit in sorted(units, key=lambda u: sorted(by_id[r].region_code for r in u.old_regions)):
        value = swings[unit]
        statuses: set[DataStatus] = set()
        for region_id in unit.old_regions:
            statuses |= old_statuses.get(region_id, set())
        for region_id in unit.new_regions:
            statuses |= new_statuses.get(region_id, set())
        out_units.append(
            SwingUnit(
                old_region_codes=sorted(by_id[r].region_code for r in unit.old_regions),
                new_region_codes=sorted(by_id[r].region_code for r in unit.new_regions),
                old_share=share(unit.old_regions, old_data),
                new_share=share(unit.new_regions, new_data),
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
        sources=await _sources(session, old_sources | new_sources),
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
        data, _, sources = await _party_area_votes(session, election, party, regions)
        votes = await _votes(session, election, [r.id for r in regions]) if regions else {}
        source_ids |= sources
        rows: list[PartyRegionResult] = []
        for region in regions:
            vote = votes.get(region.id, {}).get(party.party_code)
            area = data[region.id]
            if not contested:
                share = Percentage(value=None, unavailable=Unavailable.NOT_CONTESTED.value)
            else:
                share = _share(
                    area.party_votes, area.valid_votes, f"{party.party_code} {region.region_code}"
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
