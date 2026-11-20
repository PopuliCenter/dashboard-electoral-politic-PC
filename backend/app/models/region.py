"""Wilayah dan padanannya antar pemilu."""

import uuid
from datetime import date

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pg_enum
from app.models.enums import CrosswalkRelation, RegionLevel
from app.models.mixins import Timestamps, UUIDPrimaryKey


class Region(Base, UUIDPrimaryKey, Timestamps):
    """Provinsi, kabupaten/kota, dan kecamatan.

    Kode wilayah resmi (Kemendagri) adalah kunci referensi eksternal; kode yang
    sama bisa muncul lebih dari sekali bila masa berlakunya berbeda, karena itu
    keunikan dipasang pada (region_code, valid_from).
    """

    __tablename__ = "regions"

    region_code: Mapped[str] = mapped_column(String(20), nullable=False)
    region_name: Mapped[str] = mapped_column(String(150), nullable=False)
    region_level: Mapped[RegionLevel] = mapped_column(
        pg_enum(RegionLevel, "region_level"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=True
    )
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    parent: Mapped["Region | None"] = relationship(
        remote_side="Region.id", back_populates="children"
    )
    children: Mapped[list["Region"]] = relationship(back_populates="parent")

    __table_args__ = (
        UniqueConstraint("region_code", "valid_from", name="uq_regions_region_code_valid_from"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="valid_until_after_valid_from",
        ),
        CheckConstraint(
            "(region_level = 'province' AND parent_id IS NULL) OR "
            "(region_level <> 'province' AND parent_id IS NOT NULL)",
            name="hanya_provinsi_tanpa_induk",
        ),
        Index("ix_regions_region_level", "region_level"),
        Index("ix_regions_parent_id", "parent_id"),
        Index("ix_regions_geometry", "geometry", postgresql_using="gist"),
    )


class RegionCrosswalk(Base, UUIDPrimaryKey, Timestamps):
    """Padanan wilayah antar tahun pemilu.

    Swing hanya boleh dihitung pada unit yang punya baris di sini (aturan data 4).
    """

    __tablename__ = "region_crosswalk"

    from_region_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False
    )
    to_region_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False
    )
    from_year: Mapped[int] = mapped_column(nullable=False)
    to_year: Mapped[int] = mapped_column(nullable=False)
    relation: Mapped[CrosswalkRelation] = mapped_column(
        pg_enum(CrosswalkRelation, "crosswalk_relation"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "from_region_id",
            "to_region_id",
            "from_year",
            "to_year",
            name="uq_region_crosswalk_pasangan",
        ),
        CheckConstraint("from_year < to_year", name="from_year_sebelum_to_year"),
        Index("ix_region_crosswalk_from_region_id", "from_region_id"),
        Index("ix_region_crosswalk_to_region_id", "to_region_id"),
    )
