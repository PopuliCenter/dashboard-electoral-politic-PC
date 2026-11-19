"""Kontrak API: prefix /api/v1 dan rute kesehatan terdaftar."""

from httpx import AsyncClient


async def test_rute_terdaftar_di_bawah_api_v1(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/health/live" in paths
