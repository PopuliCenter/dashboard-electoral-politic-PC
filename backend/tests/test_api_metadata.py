"""Metadata sumber dan riwayat versi dataset (T5.3), lewat HTTP.

Data fiktif dimuat lewat jalur muat yang sama dengan data sungguhan, di
transaksi yang selalu di-rollback.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.database import get_session
from app.datasets.staging import SourceInfo, load_into_staging
from app.importer.catalog import load_catalog
from app.importer.validator import validate_file
from app.main import app
from app.models import User
from app.models.enums import RoleCode
from app.services import auth
from tests.import_fixtures import isi_referensi_fiktif, partisipasi, suara_partai, tulis_csv

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"
SUMBER = SourceInfo(
    source_name="Rekap Uji T5.3",
    source_type="uji_rekapitulasi",
    source_url="https://kpu-uji.invalid/rekap-t53.pdf",
    collection_method="ketik_manual",
    retrieved_at=datetime(2026, 1, 15, tzinfo=UTC),
)
DATASET = "uji-t53-dpr-2024"


async def _muat(session: AsyncSession, path: Path, rows: list[dict[str, str]], name: str) -> None:
    report = validate_file(tulis_csv(path, rows), await load_catalog(session))
    assert report.passed, report.errors
    await load_into_staging(
        session, report, dataset_name=name, source=SUMBER, file_reference=path.name
    )


@pytest.fixture
async def api(session: AsyncSession, tmp_path: Path) -> AsyncGenerator[AsyncClient, None]:
    await isi_referensi_fiktif(session, tmp_path / "ref")
    # v1: kecamatan dan kab/kota; v2 hanya kecamatan (menggantikan v1).
    await _muat(
        session,
        tmp_path / "v1.csv",
        [suara_partai("00.01.02", "UJI_A", "10"), suara_partai("00.01", "UJI_A", "10")],
        DATASET,
    )
    await _muat(session, tmp_path / "v2.csv", [suara_partai("00.01.02", "UJI_A", "12")], DATASET)
    await _muat(session, tmp_path / "t.csv", [partisipasi("00.01.02")], "uji-t53-partisipasi")

    peneliti = await auth.create_user(
        session,
        "peneliti-t53@uji.invalid",
        "Peneliti Uji",
        "kata-sandi-uji-panjang",
        RoleCode.RESEARCHER,
    )

    async def override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def as_researcher() -> User:
        return peneliti

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[current_user] = as_researcher
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(current_user, None)


def _versi(body: dict[str, Any], nomor: int) -> dict[str, Any]:
    return next(v for v in body["versions"] if v["version_number"] == nomor)


async def test_daftar_sumber_dengan_metadata_lengkap(api: AsyncClient) -> None:
    body = (await api.get(f"{PREFIX}/sources")).json()
    sumber = next(s for s in body if s["name"] == SUMBER.source_name)
    assert sumber["type"] == "uji_rekapitulasi"
    assert sumber["url"] == SUMBER.source_url
    assert sumber["collection_method"] == "ketik_manual"
    assert sumber["retrieved_at"].startswith("2026-01-15")
    assert sumber["version_count"] == 3


async def test_ringkasan_dataset_menunjuk_versi_yang_berlaku(api: AsyncClient) -> None:
    body = (await api.get(f"{PREFIX}/datasets")).json()
    dpr = next(d for d in body if d["dataset_name"] == DATASET)
    assert (dpr["latest_version"], dpr["version_count"]) == (2, 2)
    current = dpr["current"]
    assert current["version_number"] == 2
    assert (current["record_kind"], current["election_type"], current["election_year"]) == (
        "party_votes",
        "legislative_dpr",
        2024,
    )
    assert current["region_levels"] == ["district"]
    assert current["record_count"] == 1
    assert current["validation_status"] == "pending"
    assert current["data_status"] == "official"
    assert current["file_reference"].startswith("v2.csv sha256:")


async def test_riwayat_versi_dengan_penggantian_dan_peringatan(api: AsyncClient) -> None:
    body = (await api.get(f"{PREFIX}/datasets/{DATASET}")).json()
    assert [v["version_number"] for v in body["versions"]] == [2, 1]

    v1 = _versi(body, 1)
    assert v1["current"] is False and v1["superseded_by"] == 2
    assert v1["record_kind"] is None  # barisnya sudah digantikan

    v2 = _versi(body, 2)
    (muat,) = [e for e in v2["events"] if e["action"] == "dataset.load_staging"]
    peringatan = muat["details"]["replacement_warnings"]
    assert any("lebih sedikit" in w and "00.01" in w for w in peringatan)


async def test_detail_sumber_dan_404(api: AsyncClient) -> None:
    sumber = next(
        s for s in (await api.get(f"{PREFIX}/sources")).json() if s["name"] == SUMBER.source_name
    )
    body = (await api.get(f"{PREFIX}/sources/{sumber['id']}")).json()
    assert {v["dataset_name"] for v in body["versions"]} == {DATASET, "uji-t53-partisipasi"}
    assert (await api.get(f"{PREFIX}/sources/{uuid.uuid4()}")).status_code == 404
    assert (await api.get(f"{PREFIX}/datasets/tidak-ada")).status_code == 404


async def test_metadata_wajib_login(session: AsyncSession) -> None:
    async def override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for path in ("/sources", "/datasets"):
                assert (await c.get(f"{PREFIX}{path}")).status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


async def test_jumlah_kueri_metadata_tidak_tumbuh_per_versi(
    session: AsyncSession, tmp_path: Path, api: AsyncClient
) -> None:
    """Review T5.3: sebelumnya 4 kueri per versi."""
    from sqlalchemy import event

    from app.services.metadata import list_datasets

    async def hitung() -> int:
        jumlah = 0

        def tambah(*_: object) -> None:
            nonlocal jumlah
            jumlah += 1

        sync_engine = session.bind.sync_engine  # type: ignore[union-attr]
        event.listen(sync_engine, "before_cursor_execute", tambah)
        try:
            await list_datasets(session)
        finally:
            event.remove(sync_engine, "before_cursor_execute", tambah)
        return jumlah

    async def tambah_versi(jumlah: int, awal: int) -> None:
        for i in range(awal, awal + jumlah):
            await _muat(
                session,
                tmp_path / f"tambah{i}.csv",
                [suara_partai("00.01.02", "UJI_A", str(20 + i))],
                DATASET,
            )
        await session.flush()

    await tambah_versi(1, 0)
    sedikit = await hitung()
    await tambah_versi(4, 1)
    assert await hitung() == sedikit


async def test_versi_ditarik_ditandai(session: AsyncSession, api: AsyncClient) -> None:
    from sqlalchemy import select

    from app.datasets.withdraw import withdraw_version
    from app.models import DatasetVersion

    v2 = await session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_name == DATASET, DatasetVersion.version_number == 2
        )
    )
    assert v2 is not None
    await withdraw_version(
        session, v2.id, reason="Uji penarikan versi", actor=None, actor_email="a@uji.invalid"
    )
    body = (await api.get(f"{PREFIX}/datasets/{DATASET}")).json()
    v2_out = _versi(body, 2)
    assert v2_out["withdrawn"] is True and v2_out["current"] is False
    assert v2_out["superseded_by"] is None
    assert _versi(body, 1)["superseded_by"] == 2
    ringkas = next(
        d for d in (await api.get(f"{PREFIX}/datasets")).json() if d["dataset_name"] == DATASET
    )
    assert ringkas["current"] is None
