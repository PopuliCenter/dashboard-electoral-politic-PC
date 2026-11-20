"""Kontestasi, partai, dan pasangan calon presiden."""

import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pg_enum
from app.models.enums import ElectionType
from app.models.mixins import Timestamps, UUIDPrimaryKey


class Election(Base, UUIDPrimaryKey, Timestamps):
    """Satu kontestasi = satu jenis pemilu pada satu tahun.

    Fase 1 memakai enam baris: 3 jenis x 2 tahun (diisi di T2.5).
    """

    __tablename__ = "elections"

    election_name: Mapped[str] = mapped_column(String(150), nullable=False)
    election_type: Mapped[ElectionType] = mapped_column(
        pg_enum(ElectionType, "election_type"), nullable=False
    )
    election_year: Mapped[int] = mapped_column(nullable=False)
    election_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint("election_type", "election_year", name="uq_elections_type_year"),
        CheckConstraint("election_year BETWEEN 1955 AND 2100", name="tahun_pemilu_masuk_akal"),
    )


class Party(Base, UUIDPrimaryKey, Timestamps):
    """Partai peserta pemilu.

    Warna partai TIDAK disimpan di sini: diambil dari konfigurasi (lihat T4.5).
    `contested_2019` dan `contested_2024` menentukan partai mana yang boleh
    dihitung swing-nya dan mana yang diberi label "baru" (aturan data 4).
    """

    __tablename__ = "parties"

    party_code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    party_name: Mapped[str] = mapped_column(String(150), nullable=False)
    party_abbreviation: Mapped[str | None] = mapped_column(String(30), nullable=True)
    contested_2019: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    contested_2024: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint("contested_2019 OR contested_2024", name="partai_ikut_minimal_satu_pemilu"),
    )


class CandidatePair(Base, UUIDPrimaryKey, Timestamps):
    """Pasangan calon presiden dan wakil presiden.

    Hanya identitas pasangan; profil kandidat ditunda ke fase 2+ (CLAUDE.md).
    """

    __tablename__ = "candidate_pairs"

    election_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("elections.id", ondelete="RESTRICT"), nullable=False
    )
    pair_number: Mapped[int] = mapped_column(nullable=False)
    president_name: Mapped[str] = mapped_column(String(150), nullable=False)
    vice_president_name: Mapped[str] = mapped_column(String(150), nullable=False)

    __table_args__ = (
        UniqueConstraint("election_id", "pair_number", name="uq_candidate_pairs_election_nomor"),
        CheckConstraint("pair_number > 0", name="nomor_urut_positif"),
    )
