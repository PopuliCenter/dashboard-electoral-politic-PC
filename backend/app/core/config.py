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

    # Daftar dipisah koma, bukan JSON, supaya mudah ditulis di .env
    cors_origins: str = "http://localhost:3000"

    # Folder data/reference di dalam kontainer api (di-mount read-only).
    reference_data_dir: str = "/data/reference"

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
