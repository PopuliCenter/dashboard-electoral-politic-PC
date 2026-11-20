"""Hasil pemilu: suara partai, suara pasangan calon, dan partisipasi.

`vote_share` TIDAK disimpan di sini. Ia dihitung dari `vote_count` dan suara sah
dalam kontestasi dan wilayah yang sama (CLAUDE.md bagian Formula).
"""

import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pg_enum
from app.models.enums import DataStatus
from app.models.mixins import Timestamps, UUIDPrimaryKey


class ElectionResult(Base, UUIDPrimaryKey, Timestamps):
    """Suara satu partai, pada satu kontestasi, di satu wilayah."""

    __tablename__ = "election_results"

    election_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("elections.id", ondelete="RESTRICT"), nullable=False
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False
    )
    vote_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    data_status: Mapped[DataStatus] = mapped_column(
        pg_enum(DataStatus, "data_status"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "election_id",
            "region_id",
            "party_id",
            name="uq_election_results_kontestasi_wilayah_partai",
        ),
        CheckConstraint("vote_count >= 0", name="suara_non_negatif"),
        Index("ix_election_results_election_id_region_id", "election_id", "region_id"),
        Index("ix_election_results_party_id", "party_id"),
        Index("ix_election_results_dataset_version_id", "dataset_version_id"),
    )


class CandidateResult(Base, UUIDPrimaryKey, Timestamps):
    """Suara satu pasangan calon. Hanya untuk Pilpres.

    Bahwa `election_id` menunjuk kontestasi Pilpres ditegakkan oleh validator
    impor (T3.1), bukan oleh CHECK, karena jenis kontestasi ada di tabel lain.
    """

    __tablename__ = "candidate_results"

    election_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("elections.id", ondelete="RESTRICT"), nullable=False
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_pair_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidate_pairs.id", ondelete="RESTRICT"), nullable=False
    )
    vote_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    data_status: Mapped[DataStatus] = mapped_column(
        pg_enum(DataStatus, "data_status"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "election_id",
            "region_id",
            "candidate_pair_id",
            name="uq_candidate_results_kontestasi_wilayah_paslon",
        ),
        CheckConstraint("vote_count >= 0", name="suara_non_negatif"),
        Index("ix_candidate_results_election_id_region_id", "election_id", "region_id"),
    )


class RegionTurnout(Base, UUIDPrimaryKey, Timestamps):
    """Partisipasi per kontestasi per wilayah.

    Hubungan antar angka (misal suara sah ditambah suara tidak sah sama dengan
    pengguna hak pilih) diperiksa oleh skrip rekonsiliasi T3.3 dan dilaporkan
    sebagai selisih, bukan ditegakkan sebagai CHECK yang bisa menolak data resmi
    apa adanya.
    """

    __tablename__ = "region_turnout"

    election_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("elections.id", ondelete="RESTRICT"), nullable=False
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False
    )
    registered_voters: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    voters_turned_out: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    valid_votes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    invalid_votes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    data_status: Mapped[DataStatus] = mapped_column(
        pg_enum(DataStatus, "data_status"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("election_id", "region_id", name="uq_region_turnout_kontestasi_wilayah"),
        CheckConstraint(
            "(registered_voters IS NULL OR registered_voters >= 0) AND "
            "(voters_turned_out IS NULL OR voters_turned_out >= 0) AND "
            "(valid_votes IS NULL OR valid_votes >= 0) AND "
            "(invalid_votes IS NULL OR invalid_votes >= 0)",
            name="angka_partisipasi_non_negatif",
        ),
        Index("ix_region_turnout_election_id", "election_id"),
    )
