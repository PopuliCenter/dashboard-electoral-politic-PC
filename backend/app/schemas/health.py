"""Skema respons untuk endpoint kesehatan."""

from typing import Literal

from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    connected: bool
    postgres_version: str | None = None
    postgis_version: str | None = None
    error: str | None = Field(default=None, description="Pesan singkat bila koneksi gagal")


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app_env: str
    database: DatabaseHealth


class LivenessResponse(BaseModel):
    status: Literal["ok"]
