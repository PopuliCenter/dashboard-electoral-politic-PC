"""Penulisan berkas ekspor (T5.4), tanpa database."""

import csv
import io
import uuid

from openpyxl import load_workbook

from app.schemas.electoral import Source
from app.services.export import Table, neutralize, to_csv, to_xlsx


def _table() -> Table:
    return Table(
        title="Uji",
        columns=["region_name", "vote_count", "vote_share", "vote_share_unavailable", "flag"],
        rows=[
            ["Kecamatan Uji", 300, 75.0, None, True],
            ['=HYPERLINK("http://jahat.invalid")', None, None, "data tidak tersedia", False],
        ],
    )


def test_netralisasi_formula() -> None:
    for awal in ("=", "+", "-", "@", "\t", "\r"):
        assert neutralize(f"{awal}x") == f"'{awal}x"
    assert neutralize("Kecamatan") == "Kecamatan"
    assert neutralize(-5) == -5  # angka negatif bukan teks
    assert neutralize(None) is None


def test_csv_bom_kosong_bukan_nol_dan_formula_dinetralkan() -> None:
    raw = to_csv(_table())
    assert raw.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert rows[0] == ["region_name", "vote_count", "vote_share", "vote_share_unavailable", "flag"]
    assert rows[1] == ["Kecamatan Uji", "300", "75.0", "", "ya"]
    assert rows[2][1:4] == ["", "", "data tidak tersedia"]  # kosong, bukan 0
    assert rows[2][0].startswith("'=")


def test_xlsx_berisi_tiga_lembar_dan_sel_angka() -> None:
    raw = to_xlsx(_table(), exported_by="uji@uji.invalid", filters=[("Tingkat", "district")])
    workbook = load_workbook(io.BytesIO(raw))
    assert workbook.sheetnames == ["Data", "Sumber", "Keterangan"]

    data = workbook["Data"]
    assert data["B2"].value == 300 and data["B2"].data_type == "n"
    assert data["C2"].value == 75.0
    assert data["B3"].value is None  # tidak tersedia: kosong, bukan 0
    assert data["A3"].data_type == "s" and str(data["A3"].value).startswith("'=")

    keterangan = {row[0].value: row[1].value for row in workbook["Keterangan"].iter_rows()}
    assert keterangan["Diekspor oleh"] == "uji@uji.invalid"
    assert keterangan["Tingkat"] == "district"


def test_url_sumber_di_xlsx_dinetralkan() -> None:
    """URL sumber berasal dari masukan impor; ia juga bisa berbentuk formula."""
    table = _table()
    table.sources = [
        Source(id=uuid.uuid4(), name="Dokumen Uji", type="uji", url='=HYPERLINK("x")'),
        Source(id=uuid.uuid4(), name="Tanpa URL", type="uji", url=None),
    ]
    raw = to_xlsx(table, exported_by="uji@uji.invalid", filters=[])
    sumber = list(load_workbook(io.BytesIO(raw))["Sumber"].iter_rows(min_row=2, values_only=True))
    assert sumber[0][2] == '\'=HYPERLINK("x")'
    assert sumber[1][2] is None
