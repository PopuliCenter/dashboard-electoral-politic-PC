"""Endpoint wilayah, kontestasi, dan partai (T4.1).

Belum ada autentikasi: login dan peran datang di T5.1. Endpoint ini tidak boleh
dibuka ke jaringan publik sebelum T5.1 selesai (docs/decisions.md).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models import Election, Party, Region
from app.models.enums import ElectionType, RegionLevel
from app.schemas.electoral import (
    CompareOut,
    ElectionOut,
    ElectionResultsOut,
    PartyOut,
    PartyResultsOut,
    RegionOut,
)
from app.services import results
from app.services.results import NotFoundError

router = APIRouter()


def _not_found(exc: NotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


# --------------------------------------------------------------------------- #
# Wilayah
# --------------------------------------------------------------------------- #


@router.get("/regions", response_model=list[RegionOut], tags=["regions"], summary="Daftar wilayah")
async def list_regions(
    level: RegionLevel | None = None,
    parent_id: uuid.UUID | None = None,
    on_date: date | None = Query(
        default=None, description="Hanya wilayah yang berlaku pada tanggal ini"
    ),
    session: AsyncSession = Depends(get_session),
) -> list[RegionOut]:
    query = select(Region)
    if level is not None:
        query = query.where(Region.region_level == level)
    if parent_id is not None:
        query = query.where(Region.parent_id == parent_id)
    if on_date is not None:
        query = query.where(
            Region.valid_from <= on_date,
            or_(Region.valid_until.is_(None), Region.valid_until >= on_date),
        )
    rows = (await session.scalars(query.order_by(Region.region_code, Region.valid_from))).all()
    return [results.region_out(r) for r in rows]


@router.get("/regions/{region_id}", response_model=RegionOut, tags=["regions"])
async def get_region(
    region_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> RegionOut:
    region = await session.get(Region, region_id)
    if region is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"wilayah {region_id} tidak ada")
    return results.region_out(region)


@router.get(
    "/regions/{region_id}/children",
    response_model=list[RegionOut],
    tags=["regions"],
    summary="Wilayah turunan langsung",
)
async def region_children(
    region_id: uuid.UUID,
    on_date: date | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[RegionOut]:
    if await session.get(Region, region_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"wilayah {region_id} tidak ada")
    return await list_regions(level=None, parent_id=region_id, on_date=on_date, session=session)


# --------------------------------------------------------------------------- #
# Kontestasi
# --------------------------------------------------------------------------- #


@router.get(
    "/elections", response_model=list[ElectionOut], tags=["elections"], summary="Daftar kontestasi"
)
async def list_elections(session: AsyncSession = Depends(get_session)) -> list[ElectionOut]:
    rows = (
        await session.scalars(
            select(Election).order_by(Election.election_year, Election.election_type)
        )
    ).all()
    return [results.election_out(e) for e in rows]


@router.get(
    "/elections/compare",
    response_model=CompareOut,
    tags=["elections"],
    summary="Swing satu partai antar dua pemilu, pada unit wilayah terpadankan",
)
async def compare_elections(
    election_type: ElectionType,
    party_id: uuid.UUID,
    from_year: int = 2019,
    to_year: int = 2024,
    level: RegionLevel = RegionLevel.REGENCY,
    session: AsyncSession = Depends(get_session),
) -> CompareOut:
    try:
        return await results.compare(session, election_type, from_year, to_year, level, party_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/elections/{election_id}", response_model=ElectionOut, tags=["elections"])
async def get_election(
    election_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ElectionOut:
    try:
        return results.election_out(await results.get_election(session, election_id))
    except NotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/elections/{election_id}/results",
    response_model=ElectionResultsOut,
    tags=["elections"],
    summary="Hasil satu kontestasi per wilayah",
)
async def election_results(
    election_id: uuid.UUID,
    level: RegionLevel = RegionLevel.REGENCY,
    parent_id: uuid.UUID | None = Query(
        default=None, description="Batasi ke turunan langsung wilayah ini (drill-down)"
    ),
    session: AsyncSession = Depends(get_session),
) -> ElectionResultsOut:
    try:
        election = await results.get_election(session, election_id)
        return await results.election_results(session, election, level, parent_id)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc


# --------------------------------------------------------------------------- #
# Partai
# --------------------------------------------------------------------------- #


@router.get("/parties", response_model=list[PartyOut], tags=["parties"], summary="Daftar partai")
async def list_parties(
    year: int | None = Query(default=None, description="Hanya partai yang ikut pemilu tahun ini"),
    session: AsyncSession = Depends(get_session),
) -> list[PartyOut]:
    query = select(Party)
    if year is not None:
        contested = getattr(Party, f"contested_{year}", None)
        if contested is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"tahun {year} di luar cakupan fase 1"
            )
        query = query.where(contested.is_(True))
    rows = (await session.scalars(query.order_by(Party.party_code))).all()
    return [results.party_out(p) for p in rows]


@router.get("/parties/{party_id}", response_model=PartyOut, tags=["parties"])
async def get_party(party_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> PartyOut:
    party = await session.get(Party, party_id)
    if party is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"partai {party_id} tidak ada")
    return results.party_out(party)


@router.get(
    "/parties/{party_id}/results",
    response_model=PartyResultsOut,
    tags=["parties"],
    summary="Hasil satu partai di semua tahun untuk satu jenis kontestasi",
)
async def party_results(
    party_id: uuid.UUID,
    election_type: ElectionType = ElectionType.LEGISLATIVE_DPR,
    level: RegionLevel = RegionLevel.REGENCY,
    session: AsyncSession = Depends(get_session),
) -> PartyResultsOut:
    try:
        return await results.party_results(session, party_id, election_type, level)
    except NotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
