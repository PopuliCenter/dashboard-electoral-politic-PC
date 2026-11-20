"""Katalog dan berkas impor fiktif untuk test validator T3.1.

Semua nilai jelas fiktif (aturan data 2): kode wilayah berawalan 00 yang tidak
pernah dipakai Kemendagri, partai UJI_*, dan angka suara kecil yang dibuat-buat.
"""

import csv
import io
from pathlib import Path

from app.importer.catalog import ReferenceCatalog
from app.models.enums import ElectionType, RegionLevel

WILAYAH_2019 = {
    "00": RegionLevel.PROVINCE,
    "00.01": RegionLevel.REGENCY,
    "00.01.01": RegionLevel.DISTRICT,
    "00.01.02": RegionLevel.DISTRICT,
}
# 00.01.02 dipecah sebelum 2024: 00.01.03 baru, 00.01.02 tidak berlaku lagi.
WILAYAH_2024 = {
    "00": RegionLevel.PROVINCE,
    "00.01": RegionLevel.REGENCY,
    "00.01.01": RegionLevel.DISTRICT,
    "00.01.03": RegionLevel.DISTRICT,
}


def katalog_fiktif() -> ReferenceCatalog:
    elections = frozenset((t, y) for t in ElectionType for y in (2019, 2024))
    return ReferenceCatalog(
        elections=elections,
        party_years={
            "UJI_A": frozenset({2019, 2024}),
            "UJI_B": frozenset({2019}),
            "UJI_C": frozenset({2024}),
        },
        candidate_pairs=frozenset({(2019, 1), (2019, 2), (2024, 1), (2024, 2), (2024, 3)}),
        regions={(t, y): WILAYAH_2019 if y == 2019 else WILAYAH_2024 for t, y in elections},
    )


def suara_partai(
    region: str = "00.01.01",
    party: str = "UJI_A",
    votes: str = "100",
    *,
    jenis: str = "legislative_dpr",
    tahun: str = "2024",
    status: str = "official",
) -> dict[str, str]:
    return {
        "election_type": jenis,
        "election_year": tahun,
        "region_code": region,
        "party_code": party,
        "vote_count": votes,
        "data_status": status,
    }


def suara_paslon(
    region: str = "00.01.01",
    pair: str = "1",
    votes: str = "100",
    *,
    jenis: str = "presidential",
    tahun: str = "2024",
    status: str = "official",
) -> dict[str, str]:
    return {
        "election_type": jenis,
        "election_year": tahun,
        "region_code": region,
        "pair_number": pair,
        "vote_count": votes,
        "data_status": status,
    }


def partisipasi(
    region: str = "00.01.01",
    dpt: str = "1000",
    hadir: str = "800",
    sah: str = "780",
    tidak_sah: str = "20",
    *,
    jenis: str = "legislative_dpr",
    tahun: str = "2024",
    status: str = "official",
) -> dict[str, str]:
    return {
        "election_type": jenis,
        "election_year": tahun,
        "region_code": region,
        "registered_voters": dpt,
        "voters_turned_out": hadir,
        "valid_votes": sah,
        "invalid_votes": tidak_sah,
        "data_status": status,
    }


def tulis_csv(path: Path, rows: list[dict[str, str]], *, delimiter: str = ",") -> Path:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=list(rows[0]), delimiter=delimiter, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")
    return path
