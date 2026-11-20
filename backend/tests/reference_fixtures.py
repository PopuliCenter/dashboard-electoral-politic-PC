"""Pembangun berkas data referensi fiktif untuk test seed (T2.5).

Semua nilai jelas fiktif (aturan data 2): nama "Partai A", nama calon "Calon
Uji", sumber di domain `.invalid` yang dicadangkan dan tidak pernah ada, dan
nomor urut 900-an yang mustahil bentrok dengan nomor urut asli di database
pengembangan.
"""

import csv
import io
from pathlib import Path

from app.seed.reference import CANDIDATE_PAIR_COLUMNS, ELECTION_COLUMNS, PARTY_COLUMNS

SUMBER_2019 = "https://kpu-uji.invalid/sk-nomor-urut-2019"
SUMBER_2024 = "https://kpu-uji.invalid/sk-nomor-urut-2024"
SUMBER = "https://kpu-uji.invalid/jadwal"


def partai(
    kode: str,
    nama: str,
    *,
    nomor_2019: int | str | None = None,
    nomor_2024: int | str | None = None,
    singkatan: str | None = None,
    verified_by: str = "",
    notes: str = "",
) -> dict[str, str]:
    return {
        "party_code": kode,
        "party_name": nama,
        "party_abbreviation": singkatan if singkatan is not None else kode,
        "ballot_number_2019": "" if nomor_2019 is None else str(nomor_2019),
        "ballot_number_2024": "" if nomor_2024 is None else str(nomor_2024),
        "source_2019": SUMBER_2019 if nomor_2019 is not None else "",
        "source_2024": SUMBER_2024 if nomor_2024 is not None else "",
        "verified_by": verified_by,
        "notes": notes,
    }


def partai_fiktif() -> list[dict[str, str]]:
    """A ikut keduanya, B hanya 2019, C hanya 2024 (partai "baru")."""
    return [
        partai("UJI_A", "Partai A", nomor_2019=901, nomor_2024=901),
        partai("UJI_B", "Partai B", nomor_2019=902),
        partai("UJI_C", "Partai C", nomor_2024=903),
    ]


def kontestasi_fiktif(verified_by: str = "") -> list[dict[str, str]]:
    baris = []
    for tahun, tanggal in ((2019, "2019-01-01"), (2024, "2024-01-01")):
        for jenis, label in (
            ("presidential", "Presiden"),
            ("legislative_dpr", "DPR"),
            ("legislative_dprd_province", "DPRD Provinsi"),
        ):
            baris.append(
                {
                    "election_type": jenis,
                    "election_year": str(tahun),
                    "election_date": tanggal,
                    "election_name": f"Pemilu Uji {label} {tahun}",
                    "source": SUMBER,
                    "verified_by": verified_by,
                }
            )
    return baris


def paslon_fiktif(verified_by: str = "") -> list[dict[str, str]]:
    return [
        {
            "election_year": str(tahun),
            "pair_number": str(nomor),
            "president_name": f"Calon Uji {tahun}-{nomor}",
            "vice_president_name": f"Wakil Uji {tahun}-{nomor}",
            "source": SUMBER,
            "verified_by": verified_by,
        }
        for tahun in (2019, 2024)
        for nomor in (1, 2)
    ]


def _csv(columns: tuple[str, ...], rows: list[dict[str, str]], delimiter: str) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(columns),
        delimiter=delimiter,
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def tulis_referensi(
    folder: Path,
    *,
    parties: list[dict[str, str]] | None = None,
    elections: list[dict[str, str]] | None = None,
    pairs: list[dict[str, str]] | None = None,
    delimiter: str = ",",
    bom: bool = False,
    party_columns: tuple[str, ...] = PARTY_COLUMNS,
) -> Path:
    """Tulis ketiga berkas ke `folder`. Nilai None berarti pakai data fiktif bawaan."""
    folder.mkdir(parents=True, exist_ok=True)
    prefix = "﻿" if bom else ""
    isi = {
        "parties.csv": _csv(
            party_columns, partai_fiktif() if parties is None else parties, delimiter
        ),
        "elections.csv": _csv(
            ELECTION_COLUMNS, kontestasi_fiktif() if elections is None else elections, delimiter
        ),
        "candidate_pairs.csv": _csv(
            CANDIDATE_PAIR_COLUMNS, paslon_fiktif() if pairs is None else pairs, delimiter
        ),
    }
    for nama, teks in isi.items():
        (folder / nama).write_bytes((prefix + teks).encode("utf-8"))
    return folder
