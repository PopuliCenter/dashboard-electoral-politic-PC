"""Endpoint wilayah, kontestasi, dan partai (T4.1), dengan data fiktif di-rollback.

Database pengembangan bisa berisi partai dan paslon asli. Supaya daftar peserta
pasti, fixture menghapus referensi non-fiktif DI DALAM transaksi test yang
selalu di-rollback; database tidak pernah berubah. Angka suara fiktif dimuat
lewat jalur muat yang sama dengan data sungguhan (load_into_staging).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.database import get_session
from app.datasets.staging import SourceInfo, load_into_staging
from app.importer.catalog import load_catalog
from app.importer.validator import validate_file
from app.main import app
from app.models import CandidatePair, Election, Party, Region, RegionCrosswalk, User
from app.models.enums import CrosswalkRelation, ElectionType, RoleCode
from app.services import auth
from tests.import_fixtures import (
    isi_referensi_fiktif,
    partisipasi,
    suara_partai,
    suara_paslon,
    tulis_csv,
)

pytestmark = pytest.mark.integration

SUMBER = SourceInfo(
    source_name="Dokumen Uji T4.1", source_type="uji", source_url="https://kpu-uji.invalid/t41"
)
PREFIX = "/api/v1"


async def _muat(session: AsyncSession, path: Path, rows: list[dict[str, str]], name: str) -> None:
    report = validate_file(tulis_csv(path, rows), await load_catalog(session))
    assert report.passed, report.errors
    await load_into_staging(
        session, report, dataset_name=name, source=SUMBER, file_reference=path.name
    )


async def _id(session: AsyncSession, model: Any, column: Any, value: object) -> uuid.UUID:
    found = await session.scalar(select(model.id).where(column == value))
    assert found is not None, value
    return found  # type: ignore[no-any-return]


@pytest.fixture
async def api(session: AsyncSession, tmp_path: Path) -> AsyncGenerator[AsyncClient, None]:
    await isi_referensi_fiktif(session, tmp_path / "ref")
    # Hanya referensi fiktif yang tersisa di transaksi ini (di-rollback).
    await session.execute(delete(Party).where(~Party.party_code.like("UJI\\_%")))
    await session.execute(delete(CandidatePair).where(CandidatePair.pair_number > 2))

    await _muat(
        session,
        tmp_path / "dpr2024.csv",
        [
            suara_partai("00.01.02", "UJI_A", "300"),
            suara_partai("00.01.02", "UJI_C", "100"),
            suara_partai("00.01", "UJI_A", "300"),
        ],
        "uji-dpr-2024",
    )
    await _muat(
        session,
        tmp_path / "t2024.csv",
        [
            partisipasi("00.01.02", dpt="1000", hadir="800", sah="400", tidak_sah="400"),
            partisipasi("00.01", dpt="1000", hadir="800", sah="400", tidak_sah="400"),
        ],
        "uji-partisipasi-dpr-2024",
    )
    await _muat(
        session,
        tmp_path / "dpr2019.csv",
        [
            suara_partai("00.01.01", "UJI_A", "200", tahun="2019"),
            suara_partai("00.01.01", "UJI_B", "300", tahun="2019"),
        ],
        "uji-dpr-2019",
    )
    await _muat(
        session,
        tmp_path / "t2019.csv",
        [partisipasi("00.01.01", sah="500", tahun="2019")],
        "uji-partisipasi-dpr-2019",
    )
    await _muat(
        session,
        tmp_path / "pilpres.csv",
        [suara_paslon("00.01.02", "1", "60"), suara_paslon("00.01.02", "2", "60")],
        "uji-pilpres-2024",
    )
    # Data mustahil: suara melebihi suara sah.
    await _muat(
        session,
        tmp_path / "dprd.csv",
        [suara_partai("00.01.02", "UJI_A", "300", jenis="legislative_dprd_province")],
        "uji-dprd-2024",
    )
    await _muat(
        session,
        tmp_path / "tdprd.csv",
        [partisipasi("00.01.02", sah="100", jenis="legislative_dprd_province")],
        "uji-partisipasi-dprd-2024",
    )
    # 00.01.01 (2019) berganti kode menjadi 00.01.02 (2024).
    session.add(
        RegionCrosswalk(
            from_region_id=await _id(session, Region, Region.region_code, "00.01.01"),
            to_region_id=await _id(session, Region, Region.region_code, "00.01.02"),
            from_year=2019,
            to_year=2024,
            relation=CrosswalkRelation.RECODED,
        )
    )
    await session.flush()

    async def override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    # Endpoint data wajib login (T5.1); alur login sendiri diuji di test_auth_db.py.
    peneliti = await auth.create_user(
        session,
        "peneliti-t41@uji.invalid",
        "Peneliti Uji",
        "kata-sandi-uji-panjang",
        RoleCode.RESEARCHER,
    )

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


async def test_tanpa_login_ditolak(session: AsyncSession) -> None:
    async def override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for path in ("/elections", "/regions", "/parties"):
                assert (await c.get(f"{PREFIX}{path}")).status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


async def _election_id(session: AsyncSession, election_type: ElectionType, year: int) -> str:
    found = await session.scalar(
        select(Election.id).where(
            Election.election_type == election_type, Election.election_year == year
        )
    )
    assert found is not None
    return str(found)


def _region(body: dict[str, Any], code: str) -> dict[str, Any]:
    return next(r for r in body["regions"] if r["region"]["code"] == code)


def _item(region: dict[str, Any], key: str) -> dict[str, Any]:
    return next(i for i in region["results"] if i["key"] == key)


# --------------------------------------------------------------------------- #
# Wilayah dan kontestasi
# --------------------------------------------------------------------------- #


async def test_daftar_kontestasi(api: AsyncClient) -> None:
    body = (await api.get(f"{PREFIX}/elections")).json()
    assert {(e["type"], e["year"]) for e in body} >= {
        (t.value, y) for t in ElectionType for y in (2019, 2024)
    }


async def test_wilayah_menurut_tanggal_berlaku(api: AsyncClient) -> None:
    body = (
        await api.get(f"{PREFIX}/regions", params={"level": "district", "on_date": "2024-06-01"})
    ).json()
    codes = {r["code"] for r in body}
    assert "00.01.02" in codes and "00.01.01" not in codes


async def test_turunan_wilayah(api: AsyncClient, session: AsyncSession) -> None:
    kab = await _id(session, Region, Region.region_code, "00.01")
    body = (await api.get(f"{PREFIX}/regions/{kab}/children")).json()
    assert {r["code"] for r in body} == {"00.01.01", "00.01.02"}
    assert (await api.get(f"{PREFIX}/regions/{uuid.uuid4()}/children")).status_code == 404


async def test_kontestasi_tidak_dikenal_404(api: AsyncClient) -> None:
    response = await api.get(f"{PREFIX}/elections/{uuid.uuid4()}/results")
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Hasil satu kontestasi
# --------------------------------------------------------------------------- #


async def test_hasil_dpr_per_kecamatan(api: AsyncClient, session: AsyncSession) -> None:
    eid = await _election_id(session, ElectionType.LEGISLATIVE_DPR, 2024)
    body = (await api.get(f"{PREFIX}/elections/{eid}/results", params={"level": "district"})).json()

    kec = _region(body, "00.01.02")
    a = _item(kec, "UJI_A")
    assert a["vote_count"] == 300
    assert a["vote_share"] == {"value": 75.0, "unavailable": None}
    assert a["data_status"] == "official" and a["source_id"]
    assert _item(kec, "UJI_C")["vote_share"]["value"] == 25.0
    # UJI_B tidak ikut 2024, jadi bukan peserta.
    assert {i["key"] for i in kec["results"]} == {"UJI_A", "UJI_C"}
    assert kec["leader"] == {"keys": ["UJI_A"], "tie": False, "margin": 200, "unavailable": None}
    assert kec["turnout"]["turnout"]["value"] == 80.0
    assert kec["data_statuses"] == ["official"]
    assert any(s["name"] == SUMBER.source_name for s in body["sources"])


async def test_peserta_tanpa_angka_tidak_ditaksir(api: AsyncClient, session: AsyncSession) -> None:
    eid = await _election_id(session, ElectionType.LEGISLATIVE_DPR, 2024)
    body = (await api.get(f"{PREFIX}/elections/{eid}/results", params={"level": "regency"})).json()
    kab = _region(body, "00.01")
    c = _item(kab, "UJI_C")
    assert c["vote_count"] is None
    assert c["vote_share"] == {"value": None, "unavailable": "data tidak tersedia"}
    assert c["data_status"] is None
    assert kab["leader"]["unavailable"] == "data belum lengkap"
    assert kab["leader"]["keys"] == []


async def test_pilpres_seri_dan_tanpa_suara_sah(api: AsyncClient, session: AsyncSession) -> None:
    eid = await _election_id(session, ElectionType.PRESIDENTIAL, 2024)
    body = (await api.get(f"{PREFIX}/elections/{eid}/results", params={"level": "district"})).json()
    kec = _region(body, "00.01.02")
    assert kec["leader"] == {"keys": ["1", "2"], "tie": True, "margin": 0, "unavailable": None}
    assert _item(kec, "1")["vote_share"]["unavailable"] == "data tidak tersedia"
    assert kec["turnout"]["turnout"]["unavailable"] == "data tidak tersedia"


async def test_data_mustahil_tidak_menjatuhkan_halaman(
    api: AsyncClient, session: AsyncSession
) -> None:
    eid = await _election_id(session, ElectionType.LEGISLATIVE_DPRD_PROVINCE, 2024)
    response = await api.get(f"{PREFIX}/elections/{eid}/results", params={"level": "district"})
    assert response.status_code == 200
    a = _item(_region(response.json(), "00.01.02"), "UJI_A")
    assert a["vote_count"] == 300
    assert a["vote_share"] == {"value": None, "unavailable": "data tidak konsisten"}


async def test_drill_down_ke_turunan(api: AsyncClient, session: AsyncSession) -> None:
    eid = await _election_id(session, ElectionType.LEGISLATIVE_DPR, 2024)
    kab = await _id(session, Region, Region.region_code, "00.01")
    body = (
        await api.get(
            f"{PREFIX}/elections/{eid}/results", params={"level": "district", "parent_id": str(kab)}
        )
    ).json()
    assert [r["region"]["code"] for r in body["regions"]] == ["00.01.02"]


# --------------------------------------------------------------------------- #
# Perbandingan
# --------------------------------------------------------------------------- #


async def test_swing_lewat_padanan_wilayah(api: AsyncClient, session: AsyncSession) -> None:
    party = await _id(session, Party, Party.party_code, "UJI_A")
    body = (
        await api.get(
            f"{PREFIX}/elections/compare",
            params={
                "election_type": "legislative_dpr",
                "party_id": str(party),
                "level": "district",
            },
        )
    ).json()
    (unit,) = body["units"]
    assert (unit["old_region_codes"], unit["new_region_codes"]) == (["00.01.01"], ["00.01.02"])
    assert unit["old_share"]["value"] == 40.0  # 200 / 500
    assert unit["new_share"]["value"] == 75.0  # 300 / 400
    assert unit["swing"]["value"] == pytest.approx(35.0)
    assert body["unmatched_old_region_codes"] == []


async def test_partai_baru_tidak_punya_swing(api: AsyncClient, session: AsyncSession) -> None:
    party = await _id(session, Party, Party.party_code, "UJI_C")
    body = (
        await api.get(
            f"{PREFIX}/elections/compare",
            params={
                "election_type": "legislative_dpr",
                "party_id": str(party),
                "level": "district",
            },
        )
    ).json()
    assert body["party"]["new_in_2024"] is True
    assert body["units"][0]["swing"] == {"value": None, "unavailable": "baru"}


async def test_perbandingan_pilpres_dan_partai_tidak_dikenal_ditolak(
    api: AsyncClient, session: AsyncSession
) -> None:
    party = await _id(session, Party, Party.party_code, "UJI_A")
    pilpres = await api.get(
        f"{PREFIX}/elections/compare",
        params={"election_type": "presidential", "party_id": str(party)},
    )
    assert pilpres.status_code == 422
    unknown = await api.get(
        f"{PREFIX}/elections/compare",
        params={"election_type": "legislative_dpr", "party_id": str(uuid.uuid4())},
    )
    assert unknown.status_code == 404


# --------------------------------------------------------------------------- #
# Partai
# --------------------------------------------------------------------------- #


async def test_daftar_partai_per_tahun(api: AsyncClient) -> None:
    body = (await api.get(f"{PREFIX}/parties", params={"year": 2024})).json()
    assert {p["code"] for p in body} == {"UJI_A", "UJI_C"}
    assert next(p for p in body if p["code"] == "UJI_C")["new_in_2024"] is True
    assert (await api.get(f"{PREFIX}/parties", params={"year": 2014})).status_code == 422


async def test_hasil_partai_lintas_tahun(api: AsyncClient, session: AsyncSession) -> None:
    party = await _id(session, Party, Party.party_code, "UJI_B")
    body = (await api.get(f"{PREFIX}/parties/{party}/results", params={"level": "district"})).json()
    by_year = {e["election"]["year"]: e for e in body["elections"]}
    tahun_2019 = by_year[2019]
    assert tahun_2019["contested"] is True
    kec = next(r for r in tahun_2019["regions"] if r["region"]["code"] == "00.01.01")
    assert kec["vote_count"] == 300 and kec["vote_share"]["value"] == 60.0
    assert kec["data_status"] == "official"

    tahun_2024 = by_year[2024]
    assert tahun_2024["contested"] is False
    assert all(
        r["vote_share"]["unavailable"] == "tidak ikut pemilu ini" for r in tahun_2024["regions"]
    )
    assert date.fromisoformat(tahun_2024["election"]["date"]).year == 2024
