"""Pengguna dan peran. Fase 1: Admin dan Peneliti (T5.1)."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pg_enum
from app.models.enums import RoleCode
from app.models.mixins import Timestamps, UUIDPrimaryKey


class Role(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "roles"

    role_code: Mapped[RoleCode] = mapped_column(
        pg_enum(RoleCode, "role_code"), nullable=False, unique=True
    )
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base, UUIDPrimaryKey, Timestamps):
    """Password disimpan hanya sebagai hash; tidak ada kolom password mentah."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    role: Mapped[Role] = relationship(back_populates="users")
