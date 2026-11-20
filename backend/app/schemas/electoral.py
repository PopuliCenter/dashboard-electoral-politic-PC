"""Skema respons API elektoral (T4.1).

Konvensi:

- Angka yang tidak bisa dihitung dikirim sebagai `null` disertai `unavailable`
  berisi alasannya dalam teks antarmuka (misalnya "data tidak tersedia",
  "baru"). Klien tidak boleh mengganti `null` dengan 0.
- Setiap angka hasil pemilu membawa `data_status` dan `source_id`, dan setiap
  respons hasil membawa daftar `sources` lengkap (CLAUDE.md, Konvensi).
- Persentase dikirim tanpa pembulatan; pembulatan urusan tampilan.
"""

import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.models.enums import DataStatus, ElectionType, RegionLevel


class Source(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    url: str | None


class RegionOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    level: RegionLevel
    parent_id: uuid.UUID | None
    valid_from: date
    valid_until: date | None


class ElectionOut(BaseModel):
    id: uuid.UUID
    type: ElectionType
    year: int
    date: date | None
    name: str


class PartyOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    abbreviation: str | None
    contested_2019: bool
    contested_2024: bool
    ballot_number_2019: int | None
    ballot_number_2024: int | None
    new_in_2024: bool = Field(description="Ikut 2024 tetapi tidak 2019: diberi label 'baru'")


class Percentage(BaseModel):
    value: float | None
    unavailable: str | None = Field(default=None, description="Alasan bila value null")
    data_status: DataStatus | None = Field(
        default=None,
        description="Status terlemah dari semua angka yang dipakai menghitungnya "
        "(pembilang dan penyebut)",
    )


class ItemResult(BaseModel):
    """Suara satu peserta (partai atau paslon) di satu wilayah."""

    key: str = Field(description="party_code, atau nomor urut paslon sebagai teks")
    label: str
    vote_count: int | None
    vote_share: Percentage
    data_status: DataStatus | None
    source_id: uuid.UUID | None


class Turnout(BaseModel):
    registered_voters: int | None
    voters_turned_out: int | None
    valid_votes: int | None
    invalid_votes: int | None
    turnout: Percentage
    data_status: DataStatus | None
    source_id: uuid.UUID | None


class Leader(BaseModel):
    keys: list[str] = Field(description="Lebih dari satu berarti seri")
    tie: bool
    margin: int | None
    unavailable: str | None = None
    data_status: DataStatus | None = Field(
        default=None, description="Status terlemah dari suara yang dibandingkan"
    )


class RegionResult(BaseModel):
    region: RegionOut
    results: list[ItemResult]
    turnout: Turnout
    leader: Leader
    data_statuses: list[DataStatus]


class ElectionResultsOut(BaseModel):
    election: ElectionOut
    level: RegionLevel
    regions: list[RegionResult]
    sources: list[Source]


class SwingUnit(BaseModel):
    old_region_codes: list[str]
    new_region_codes: list[str]
    old_share: Percentage
    new_share: Percentage
    swing: Percentage = Field(description="Poin persentase, baru dikurangi lama")
    data_statuses: list[DataStatus]


class CompareOut(BaseModel):
    election_type: ElectionType
    from_year: int
    to_year: int
    level: RegionLevel
    party: PartyOut
    units: list[SwingUnit]
    unmatched_old_region_codes: list[str] = Field(
        description="Wilayah lama tanpa padanan yang sah; swing-nya tidak dihitung"
    )
    unmatched_new_region_codes: list[str]
    sources: list[Source]


class PartyRegionResult(BaseModel):
    region: RegionOut
    vote_count: int | None
    vote_share: Percentage
    data_status: DataStatus | None
    source_id: uuid.UUID | None


class PartyElectionResults(BaseModel):
    election: ElectionOut
    contested: bool
    regions: list[PartyRegionResult]


class PartyResultsOut(BaseModel):
    party: PartyOut
    level: RegionLevel
    elections: list[PartyElectionResults]
    sources: list[Source]
