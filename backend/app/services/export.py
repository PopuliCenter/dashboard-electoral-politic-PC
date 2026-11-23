"""Ekspor CSV/XLSX (T5.4) dari respons yang sama dengan tampilan.

Ekspor tidak menghitung ulang apa pun: ia meratakan `ElectionResultsOut`,
`CompareOut`, dan `PartyResultsOut` yang juga dipakai peta dan halaman partai,
jadi angka di berkas selalu sama dengan angka di layar.

Aturan:

- Setiap baris membawa `data_status` dan sumbernya (CLAUDE.md, aturan data 5).
- Angka yang tidak tersedia dibiarkan KOSONG dengan kolom alasan; tidak pernah 0.
- CSV: UTF-8 dengan BOM, koma, titik desimal (untuk dibaca mesin). XLSX: sel
  angka sungguhan, ditambah lembar "Sumber" dan "Keterangan". Untuk Excel,
  pakai XLSX.
- Teks yang diawali = + - @ (atau tab/CR) dinetralkan dengan awalan petik,
  supaya nama wilayah atau partai tidak dieksekusi sebagai formula.
"""

import csv
import io
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from openpyxl import Workbook

from app.schemas.electoral import (
    CompareOut,
    ElectionResultsOut,
    PartyResultsOut,
    Percentage,
    Source,
)
from app.services.analytics import Unavailable

ExportFormat = Literal["csv", "xlsx"]
Cell = str | int | float | None

CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralize(value: Cell) -> Cell:
    """Cegah injeksi formula pada sel teks (CSV dan XLSX)."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


@dataclass
class Table:
    title: str
    columns: list[str]
    rows: list[list[Cell]] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    # Keterangan ekspor: (label, nilai), tampil di lembar "Keterangan".
    notes: list[tuple[str, str]] = field(default_factory=list)


def _pct(p: Percentage) -> list[Cell]:
    return [p.value, p.data_status.value if p.data_status else None, p.unavailable]


def _source_cells(source_id: uuid.UUID | None, sources: Mapping[uuid.UUID, Source]) -> list[Cell]:
    if source_id is None:
        return [None, None]
    source = sources.get(source_id)
    return [source.name if source else None, source.url if source else None]


def _many_source_cells(
    source_ids: Sequence[uuid.UUID], sources: Mapping[uuid.UUID, Source]
) -> list[Cell]:
    """Nama dan URL beberapa sumber dalam satu sel, dipisah ' | '."""
    found = [sources[i] for i in source_ids if i in sources]
    if not found:
        return [None, None]
    return [" | ".join(s.name for s in found), " | ".join(s.url or "" for s in found)]


# --------------------------------------------------------------------------- #
# Perataan respons
# --------------------------------------------------------------------------- #


def election_results_table(data: ElectionResultsOut) -> Table:
    sources = {s.id: s for s in data.sources}
    e = data.election
    table = Table(
        title=f"Hasil {e.type.value} {e.year}",
        columns=[
            "election_type",
            "election_year",
            "region_level",
            "region_code",
            "region_name",
            "participant_key",
            "participant_label",
            "vote_count",
            "vote_share",
            "vote_share_status",
            "vote_share_unavailable",
            "data_status",
            "source_name",
            "source_url",
            "valid_votes",
            # Status baris partisipasi tempat valid_votes berasal; bisa berbeda dengan
            # data_status suara peserta di baris yang sama.
            "valid_votes_status",
            "turnout",
            "turnout_status",
            "turnout_unavailable",
            "leader",
            "leader_tie",
            "margin",
            "leader_unavailable",
            "leader_status",
        ],
        sources=data.sources,
    )
    for region in data.regions:
        t = region.turnout
        leader = region.leader
        for item in region.results:
            table.rows.append(
                [
                    e.type.value,
                    e.year,
                    region.region.level.value,
                    region.region.code,
                    region.region.name,
                    item.key,
                    item.label,
                    item.vote_count,
                    *_pct(item.vote_share),
                    item.data_status.value if item.data_status else None,
                    *_source_cells(item.source_id, sources),
                    t.valid_votes,
                    t.data_status.value if t.data_status else None,
                    *_pct(t.turnout),
                    " / ".join(leader.keys) or None,
                    leader.tie if leader.keys else None,
                    leader.margin,
                    leader.unavailable,
                    leader.data_status.value if leader.data_status else None,
                ]
            )
    return table


def compare_table(data: CompareOut) -> Table:
    """Satu baris per unit padanan, ditambah satu baris per wilayah tanpa padanan.

    Wilayah tanpa padanan ditulis sebagai baris (bukan hanya catatan XLSX) supaya
    CSV juga menunjukkan wilayah mana yang dikeluarkan dari swing dan alasannya.
    """
    sources = {s.id: s for s in data.sources}
    table = Table(
        title=f"Swing {data.party.code} {data.election_type.value} {data.from_year}-{data.to_year}",
        columns=[
            "election_type",
            "party_code",
            "from_year",
            "to_year",
            "region_level",
            "old_region_codes",
            "new_region_codes",
            "old_share",
            "old_share_status",
            "old_share_unavailable",
            "new_share",
            "new_share_status",
            "new_share_unavailable",
            "swing_points",
            "swing_status",
            "swing_unavailable",
            "data_statuses",
            "source_names",
            "source_urls",
        ],
        sources=data.sources,
        notes=[
            (
                "Wilayah lama tanpa padanan",
                ", ".join(data.unmatched_old_region_codes) or "-",
            ),
            (
                "Wilayah baru tanpa padanan",
                ", ".join(data.unmatched_new_region_codes) or "-",
            ),
        ],
    )
    for unit in data.units:
        table.rows.append(
            [
                data.election_type.value,
                data.party.code,
                data.from_year,
                data.to_year,
                data.level.value,
                ", ".join(unit.old_region_codes),
                ", ".join(unit.new_region_codes),
                *_pct(unit.old_share),
                *_pct(unit.new_share),
                *_pct(unit.swing),
                ", ".join(s.value for s in unit.data_statuses) or None,
                *_many_source_cells(unit.source_ids, sources),
            ]
        )
    unmatched = Unavailable.UNMATCHED.value
    for side, codes in (
        ("old", data.unmatched_old_region_codes),
        ("new", data.unmatched_new_region_codes),
    ):
        for code in codes:
            table.rows.append(
                [
                    data.election_type.value,
                    data.party.code,
                    data.from_year,
                    data.to_year,
                    data.level.value,
                    code if side == "old" else None,
                    code if side == "new" else None,
                    None,
                    None,
                    unmatched,
                    None,
                    None,
                    unmatched,
                    None,
                    None,
                    unmatched,
                    None,
                    None,
                    None,
                ]
            )
    return table


def party_results_table(data: PartyResultsOut) -> Table:
    sources = {s.id: s for s in data.sources}
    table = Table(
        title=f"Hasil partai {data.party.code}",
        columns=[
            "party_code",
            "party_name",
            "election_type",
            "election_year",
            "contested",
            "region_level",
            "region_code",
            "region_name",
            "vote_count",
            "vote_share",
            "vote_share_status",
            "vote_share_unavailable",
            "data_status",
            "source_name",
            "source_url",
        ],
        sources=data.sources,
    )
    for election in data.elections:
        for row in election.regions:
            table.rows.append(
                [
                    data.party.code,
                    data.party.name,
                    election.election.type.value,
                    election.election.year,
                    election.contested,
                    row.region.level.value,
                    row.region.code,
                    row.region.name,
                    row.vote_count,
                    *_pct(row.vote_share),
                    row.data_status.value if row.data_status else None,
                    *_source_cells(row.source_id, sources),
                ]
            )
    return table


# --------------------------------------------------------------------------- #
# Penulisan berkas
# --------------------------------------------------------------------------- #


def _csv_cell(value: Cell) -> Cell:
    if isinstance(value, bool):
        return "ya" if value else "tidak"
    return neutralize(value)


def to_csv(table: Table) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(table.columns)
    for row in table.rows:
        writer.writerow(["" if v is None else _csv_cell(v) for v in row])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def to_xlsx(table: Table, *, exported_by: str, filters: Sequence[tuple[str, str]]) -> bytes:
    workbook = Workbook(write_only=True)

    data = workbook.create_sheet("Data")
    data.append(table.columns)
    for row in table.rows:
        data.append([neutralize(v) for v in row])

    sources = workbook.create_sheet("Sumber")
    sources.append(["source_name", "source_type", "source_url"])
    for s in table.sources:
        sources.append([neutralize(s.name), neutralize(s.type), neutralize(s.url)])

    notes = workbook.create_sheet("Keterangan")
    for label, value in [
        ("Judul", table.title),
        ("Diekspor pada (UTC)", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")),
        ("Diekspor oleh", exported_by),
        *filters,
        *table.notes,
        (
            "Catatan",
            "Sel angka kosong berarti tidak tersedia; alasannya di kolom *_unavailable. "
            "Jangan diisi 0. Status persentase adalah status terlemah dari angka yang "
            "dipakai menghitungnya.",
        ),
    ]:
        notes.append([label, neutralize(value)])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def render(
    table: Table,
    fmt: ExportFormat,
    *,
    exported_by: str,
    filters: Sequence[tuple[str, str]],
) -> tuple[bytes, str]:
    if fmt == "xlsx":
        return to_xlsx(table, exported_by=exported_by, filters=filters), XLSX_MEDIA_TYPE
    return to_csv(table), CSV_MEDIA_TYPE
