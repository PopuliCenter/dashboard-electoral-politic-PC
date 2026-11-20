"""Skema metadata sumber dan riwayat versi dataset (T5.3).

Isi mengikuti SDD 12.4: URL sumber, instansi/jenis sumber, tanggal pengambilan,
tahun data, tingkat wilayah, metode pengumpulan, jumlah record, status
validasi, dan versi dataset.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import DataStatus, ElectionType, RegionLevel, ValidationStatus


class SourceOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    url: str | None
    collection_method: str | None
    retrieved_at: datetime | None
    checksum_sha256: str | None
    notes: str | None
    version_count: int


class VersionEvent(BaseModel):
    """Satu kejadian dari audit_logs untuk versi ini (muat, promosi)."""

    action: str
    at: datetime
    details: dict[str, Any] | None


class VersionOut(BaseModel):
    id: uuid.UUID
    dataset_name: str
    version_number: int
    source_id: uuid.UUID
    source_name: str
    validation_status: ValidationStatus
    data_status: DataStatus
    record_count: int | None
    collected_at: datetime | None
    created_at: datetime
    file_reference: str | None = Field(description="Nama berkas dan checksum SHA-256")
    notes: str | None
    current: bool = Field(description="Baris hasil versi ini yang sedang dipakai")
    withdrawn: bool = Field(
        default=False, description="Barisnya ditarik dari produksi oleh Admin (lihat events)"
    )
    superseded_by: int | None = Field(
        default=None, description="Nomor versi yang menggantikan versi ini"
    )
    record_kind: str | None = Field(
        default=None, description="party_votes, candidate_votes, atau turnout (versi berlaku)"
    )
    election_type: ElectionType | None = None
    election_year: int | None = None
    region_levels: list[RegionLevel] = Field(default_factory=list)
    events: list[VersionEvent] = Field(default_factory=list)


class DatasetSummary(BaseModel):
    dataset_name: str
    current: VersionOut | None = Field(description="Versi yang barisnya sedang dipakai")
    latest_version: int
    version_count: int


class DatasetHistory(BaseModel):
    dataset_name: str
    versions: list[VersionOut] = Field(description="Terbaru lebih dulu")


class SourceDetail(BaseModel):
    source: SourceOut
    versions: list[VersionOut]
