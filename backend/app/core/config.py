"""Konfigurasi aplikasi. Semua rahasia datang dari environment, bukan dari kode."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Populi Electoral Dashboard API"
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "info"

    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://populi:ganti_untuk_produksi@db:5432/populi"

    # Database staging (T3.4): semua data baru dimuat ke sini dulu, lalu
    # dipromosikan ke database_url. Kosong berarti perintah muat dan promosi
    # menolak jalan. Di produksi letaknya di Server B (REVISI-v1.1 bagian 4).
    staging_database_url: str | None = None

    # Daftar dipisah koma, bukan JSON, supaya mudah ditulis di .env
    cors_origins: str = "http://localhost:3000"

    # Folder data/reference di dalam kontainer api (di-mount read-only).
    reference_data_dir: str = "/data/reference"

    # Sesi login (T5.1). Batas idle: sesi berakhir bila tidak dipakai selama ini.
    # Batas absolut: sesi berakhir paling lambat sekian jam setelah login.
    session_cookie_name: str = "populi_session"
    session_idle_minutes: int = 480
    session_absolute_hours: int = 12
    # Kosong berarti otomatis: Secure di semua lingkungan kecuali development
    # (pengembangan lokal memakai http://localhost).
    session_cookie_secure: bool | None = None
    login_max_failures: int = 5
    login_lock_minutes: int = 15

    @property
    def cookie_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.app_env != "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def alembic_database_url(self) -> str:
        """Alembic memakai URL yang sama; driver async sudah didukung env.py."""
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
