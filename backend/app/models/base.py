"""Base deklaratif SQLAlchemy 2. Semua model tabel mewarisi kelas ini.

Tabel inti (regions, elections, parties, election_results, dan lainnya) dibuat di T2.1.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base metadata yang dibaca Alembic autogenerate."""
