"""Test endpoint kesehatan (T0.4)."""

import pytest
from httpx import AsyncClient


async def test_liveness_tidak_butuh_database(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_melaporkan_degraded_bila_database_mati(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Database yang tidak bisa dihubungi harus menjadi 503, bukan 500."""
    from sqlalchemy.exc import OperationalError

    async def gagal(_session: object) -> dict[str, str]:
        raise OperationalError("SELECT 1", {}, Exception("koneksi ditolak"))

    monkeypatch.setattr("app.api.v1.health.ping_database", gagal)
    response = await client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"]["connected"] is False


@pytest.mark.integration
async def test_health_dengan_database_nyata(client: AsyncClient) -> None:
    """Hanya jalan bila database hidup; dipakai saat `docker compose up`."""
    response = await client.get("/api/v1/health")
    if response.status_code != 200:
        pytest.skip("database tidak tersedia di lingkungan ini")
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["connected"] is True
    assert body["database"]["postgis_version"] != "tidak terpasang"
