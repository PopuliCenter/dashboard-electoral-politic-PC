"""Endpoint kesehatan.

- `/health/live` hanya menjawab bahwa proses hidup; dipakai healthcheck kontainer.
- `/health` ikut mengecek koneksi database, sesuai kriteria T0.4.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session, ping_database
from app.schemas.health import DatabaseHealth, HealthResponse, LivenessResponse

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=LivenessResponse, summary="Cek proses hidup")
async def liveness() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get("/health", response_model=HealthResponse, summary="Cek aplikasi dan database")
async def health(
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    try:
        versions = await ping_database(session)
    except SQLAlchemyError as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="degraded",
            app_env=settings.app_env,
            database=DatabaseHealth(connected=False, error=type(exc).__name__),
        )

    return HealthResponse(
        status="ok",
        app_env=settings.app_env,
        database=DatabaseHealth(
            connected=True,
            postgres_version=versions["postgres_version"],
            postgis_version=versions["postgis_version"],
        ),
    )
