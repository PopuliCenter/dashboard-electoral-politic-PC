"""Base deklaratif SQLAlchemy 2 dan pembantu tipe ENUM."""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Nama constraint yang dapat ditebak, supaya migrasi Alembic tidak bergantung
# pada nama acak yang dibuat PostgreSQL.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base metadata yang dibaca Alembic autogenerate."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Tipe ENUM PostgreSQL yang menyimpan *nilai* enum, bukan nama anggotanya."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
