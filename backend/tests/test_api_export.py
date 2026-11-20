"""Endpoint ekspor (T5.4), dengan data fiktif yang sama dengan test API T4.1."""

# Fixture `api` dipakai ulang dari test_api_electoral; ruff mengira parameter
# bernama sama sebagai definisi ulang.
# ruff: noqa: F811

import csv
import io

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Party
from app.models.enums import ElectionType
from tests.test_api_electoral import PREFIX, SUMBER, _election_id, _id, api  # noqa: F401

pytestmark = pytest.mark.integration


def _rows(raw: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


async def test_ekspor_csv_hasil_kontestasi(api: AsyncClient, session: AsyncSession) -> None:
    eid = await _election_id(session, ElectionType.LEGISLATIVE_DPR, 2024)
    response = await api.get(
        f"{PREFIX}/elections/{eid}/results/export", params={"level": "district"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert (
        'filename="hasil_legislative_dpr_2024_district.csv"'
        in (response.headers["content-disposition"])
    )
    rows = _rows(response.content)
    a = next(r for r in rows if r["region_code"] == "00.01.02" and r["participant_key"] == "UJI_A")
    assert (a["vote_count"], a["vote_share"], a["data_status"]) == ("300", "75.0", "official")
    assert a["vote_share_status"] == "official"
    assert a["source_name"] == SUMBER.source_name and a["source_url"] == SUMBER.source_url
    assert (a["leader"], a["margin"]) == ("UJI_A", "200")


async def test_ekspor_angka_tidak_tersedia_kosong_bukan_nol(
    api: AsyncClient, session: AsyncSession
) -> None:
    eid = await _election_id(session, ElectionType.LEGISLATIVE_DPR, 2024)
    rows = _rows(
        (
            await api.get(f"{PREFIX}/elections/{eid}/results/export", params={"level": "regency"})
        ).content
    )
    c = next(r for r in rows if r["region_code"] == "00.01" and r["participant_key"] == "UJI_C")
    assert c["vote_count"] == "" and c["vote_share"] == ""
    assert c["vote_share_unavailable"] == "data tidak tersedia"
    assert c["data_status"] == ""
    assert c["leader_unavailable"] == "data belum lengkap"


async def test_ekspor_xlsx_swing(api: AsyncClient, session: AsyncSession) -> None:
    party = await _id(session, Party, Party.party_code, "UJI_A")
    response = await api.get(
        f"{PREFIX}/elections/compare/export",
        params={
            "election_type": "legislative_dpr",
            "party_id": str(party),
            "level": "district",
            "format": "xlsx",
        },
    )
    assert response.status_code == 200
    workbook = load_workbook(io.BytesIO(response.content))
    data = workbook["Data"]
    header = [c.value for c in next(data.iter_rows(max_row=1))]
    row = dict(
        zip(header, [c.value for c in next(data.iter_rows(min_row=2, max_row=2))], strict=True)
    )
    assert row["old_region_codes"] == "00.01.01" and row["new_region_codes"] == "00.01.02"
    assert row["swing_points"] == pytest.approx(35.0)
    assert {r[0].value for r in workbook["Sumber"].iter_rows(min_row=2)} == {SUMBER.source_name}


async def test_ekspor_hasil_partai_dan_jejak_audit(api: AsyncClient, session: AsyncSession) -> None:
    party = await _id(session, Party, Party.party_code, "UJI_B")
    response = await api.get(
        f"{PREFIX}/parties/{party}/results/export", params={"level": "district"}
    )
    rows = _rows(response.content)
    tahun_2019 = next(
        r for r in rows if r["election_year"] == "2019" and r["region_code"] == "00.01.01"
    )
    assert (tahun_2019["vote_count"], tahun_2019["vote_share"]) == ("300", "60.0")
    tahun_2024 = [r for r in rows if r["election_year"] == "2024"]
    assert tahun_2024 and all(
        r["vote_share_unavailable"] == "tidak ikut pemilu ini" for r in tahun_2024
    )

    audit = (await session.scalars(select(AuditLog).where(AuditLog.action == "export"))).all()
    assert any(
        a.payload and a.payload["path"].endswith("/results/export") and a.payload["rows"]
        for a in audit
    )


async def test_ekspor_menolak_parameter_keliru(api: AsyncClient, session: AsyncSession) -> None:
    eid = await _election_id(session, ElectionType.LEGISLATIVE_DPR, 2024)
    salah_format = await api.get(
        f"{PREFIX}/elections/{eid}/results/export", params={"format": "pdf"}
    )
    assert salah_format.status_code == 422
    party = await _id(session, Party, Party.party_code, "UJI_A")
    pilpres = await api.get(
        f"{PREFIX}/elections/compare/export",
        params={"election_type": "presidential", "party_id": str(party)},
    )
    assert pilpres.status_code == 422
