"""Enum domain. Nilainya ikut dibuat sebagai tipe ENUM PostgreSQL.

Nilai enum adalah bagian dari kontrak data: mengubahnya butuh migrasi Alembic.
"""

from enum import StrEnum


class RegionLevel(StrEnum):
    """Tingkat wilayah. Fase 1 berhenti di kecamatan (`district`)."""

    PROVINCE = "province"
    REGENCY = "regency"
    DISTRICT = "district"


class ElectionType(StrEnum):
    """Jenis kontestasi. Tidak pernah dicampur dalam kueri maupun agregasi."""

    PRESIDENTIAL = "presidential"
    LEGISLATIVE_DPR = "legislative_dpr"
    LEGISLATIVE_DPRD_PROVINCE = "legislative_dprd_province"


class DataStatus(StrEnum):
    """Status setiap baris hasil. Ikut tampil di UI dan file ekspor."""

    OFFICIAL = "official"
    UNOFFICIAL = "unofficial"
    INTERNAL_AGGREGATE = "internal_aggregate"


class CrosswalkRelation(StrEnum):
    """Hubungan wilayah 2019 ke 2024."""

    SAME = "same"
    SPLIT = "split"
    MERGED = "merged"
    RECODED = "recoded"


class ValidationStatus(StrEnum):
    """Status versi dataset. Hanya `passed` yang boleh dipromosikan ke produksi."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class JobStatus(StrEnum):
    """Status pekerjaan impor di tabel `ingestion_jobs`."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RoleCode(StrEnum):
    """Dua peran fase 1."""

    ADMIN = "admin"
    RESEARCHER = "researcher"
