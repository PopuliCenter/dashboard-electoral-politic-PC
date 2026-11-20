"""Asal-usul data: sumber, versi dataset, pekerjaan impor, dan jejak audit.

Setiap baris hasil wajib menunjuk ke `data_sources` dan `dataset_versions`
(aturan data 5).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pg_enum
from app.models.enums import DataStatus, JobStatus, ValidationStatus
from app.models.mixins import Timestamps, UUIDPrimaryKey


class DataSource(Base, UUIDPrimaryKey, Timestamps):
    """Dokumen atau layanan asal data (rekapitulasi KPU, Kemendagri, BIG, BPS)."""

    __tablename__ = "data_sources"

    source_name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    collection_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DatasetVersion(Base, UUIDPrimaryKey, Timestamps):
    """Satu versi dataset hasil impor.

    Dokumen mentah tidak pernah diubah; koreksi menjadi versi baru (aturan data 8).
    Hanya versi dengan `validation_status = 'passed'` yang boleh dipromosikan.
    """

    __tablename__ = "dataset_versions"

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    record_count: Mapped[int | None] = mapped_column(nullable=True)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        pg_enum(ValidationStatus, "validation_status"),
        nullable=False,
        default=ValidationStatus.PENDING,
    )
    data_status: Mapped[DataStatus] = mapped_column(
        pg_enum(DataStatus, "data_status"), nullable=False
    )
    file_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("dataset_name", "version_number", name="uq_dataset_versions_nama_versi"),
        CheckConstraint("version_number > 0", name="nomor_versi_positif"),
        CheckConstraint(
            "record_count IS NULL OR record_count >= 0", name="jumlah_baris_non_negatif"
        ),
        Index("ix_dataset_versions_source_id", "source_id"),
    )


class IngestionJob(Base, UUIDPrimaryKey, Timestamps):
    """Catatan satu kali jalan impor atau job terjadwal.

    Menggantikan orkestrator (REVISI-v1.1 bagian 1: cron + tabel ini).
    """

    __tablename__ = "ingestion_jobs"

    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"), nullable=False, default=JobStatus.QUEUED
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True
    )
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    record_count: Mapped[int | None] = mapped_column(nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_ingestion_jobs_status", "status"),)


class AuditLog(Base, UUIDPrimaryKey):
    """Jejak perubahan. Hanya ditambah, tidak pernah diubah atau dihapus."""

    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_audit_logs_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )
