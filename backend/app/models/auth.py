"""Pengguna, peran, dan sesi login. Fase 1: Admin dan Peneliti (T5.1)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Uuid
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
    # Penguncian sementara setelah login gagal berulang (T5.1).
    failed_login_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role: Mapped[Role] = relationship(back_populates="users", lazy="joined")


class UserSession(Base, UUIDPrimaryKey):
    """Sesi login server-side.

    Yang disimpan hanya SHA-256 dari token; token mentahnya hanya ada di cookie
    peramban. Bocornya tabel ini tidak memberi siapa pun sesi yang bisa dipakai.
    Sesi dicabut dengan mengisi `revoked_at`, bukan dihapus, supaya jejaknya ada.
    """

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)

    user: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (Index("ix_user_sessions_user_id", "user_id"),)
