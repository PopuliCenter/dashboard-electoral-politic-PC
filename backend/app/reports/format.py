"""Menyajikan laporan kelengkapan sebagai teks atau CSV (T3.5)."""

import csv
import io

from app.models.enums import DataStatus, RegionLevel
from app.reports.completeness import (
    TURNOUT_FIELDS,
    CompletenessReport,
    LevelSummary,
    RegionDetail,
    VoteCoverage,
)

LEVEL_LABEL = {
    RegionLevel.PROVINCE: "provinsi",
    RegionLevel.REGENCY: "kab/kota",
    RegionLevel.DISTRICT: "kecamatan",
}
TURNOUT_LABEL = {
    "registered_voters": "DPT",
    "voters_turned_out": "hadir",
    "valid_votes": "sah",
    "invalid_votes": "tdk sah",
}
STATUS_LABEL = {
    DataStatus.OFFICIAL: "resmi",
    DataStatus.UNOFFICIAL: "tdk resmi",
    DataStatus.INTERNAL_AGGREGATE: "agregat",
}

# Wilayah yang belum lengkap yang dicetak per tingkat dalam mode teks rinci.
MAX_DETAIL_LINES = 50


def _pct(summary: LevelSummary, count: int) -> str:
    value = summary.percent(count)
    if value is None:
        return "-"
    # Desimal koma, sesuai kebiasaan pembaca laporan.
    return f"{count} ({value:.1f}%)".replace(".", ",")


def render_text(report: CompletenessReport, *, database: str, detail: bool) -> str:
    out: list[str] = [f"Kelengkapan data, database {database}", ""]
    for warning in report.warnings:
        out.append(f"! {warning}")
    if report.warnings:
        out.append("")

    headers = [
        "tingkat",
        "wilayah",
        "suara lengkap",
        "sebagian",
        "kosong",
        *(TURNOUT_LABEL[f] for f in TURNOUT_FIELDS),
        *(STATUS_LABEL[s] for s in DataStatus),
        "campur",
    ]
    current = None
    rows: list[list[str]] = []

    def flush() -> None:
        if not rows:
            return
        widths = [max(len(r[i]) for r in [headers, *rows]) for i in range(len(headers))]
        out.append("  " + "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True)))
        for r in rows:
            out.append("  " + "  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)))
        out.append("")
        rows.clear()

    for s in report.summaries:
        key = (s.election_type, s.election_year)
        if key != current:
            flush()
            out.append(f"{s.election_type.value} {s.election_year}")
            current = key
        rows.append(
            [
                LEVEL_LABEL[s.level],
                str(s.regions),
                _pct(s, s.coverage[VoteCoverage.COMPLETE]),
                _pct(s, s.coverage[VoteCoverage.PARTIAL]),
                _pct(s, s.coverage[VoteCoverage.EMPTY]),
                *(_pct(s, s.turnout[f]) for f in TURNOUT_FIELDS),
                *(_pct(s, s.statuses[st]) for st in DataStatus),
                str(s.mixed_status),
            ]
        )
    flush()

    if detail:
        out.extend(_detail_lines(report))
    out.append(
        "Persentase terhadap jumlah wilayah yang berlaku pada hari pemungutan suara. "
        "Laporan ini tidak menilai benar-salahnya angka (itu rekonsiliasi)."
    )
    return "\n".join(out) + "\n"


def _detail_lines(report: CompletenessReport) -> list[str]:
    out = ["Wilayah yang suaranya belum lengkap", ""]
    groups: dict[tuple[str, int, RegionLevel], list[RegionDetail]] = {}
    for d in report.details:
        if d.coverage is not VoteCoverage.COMPLETE:
            groups.setdefault((d.election_type.value, d.election_year, d.region.level), []).append(
                d
            )
    if not report.details:
        return ["Tidak ada wilayah untuk dirinci.", ""]
    if not groups:
        return ["Semua wilayah sudah lengkap suaranya.", ""]
    for (election_type, year, level), details in groups.items():
        out.append(f"{election_type} {year}, {LEVEL_LABEL[level]}")
        for d in details[:MAX_DETAIL_LINES]:
            missing = "semua" if d.coverage is VoteCoverage.EMPTY else ", ".join(d.missing_items)
            out.append(f"  {d.region.code} {d.region.name}: kurang {missing}")
        if len(details) > MAX_DETAIL_LINES:
            out.append(
                f"  ... dan {len(details) - MAX_DETAIL_LINES} wilayah lain (pakai --format csv)"
            )
        out.append("")
    return out


CSV_COLUMNS = (
    "election_type",
    "election_year",
    "region_level",
    "region_code",
    "region_name",
    "vote_coverage",
    "missing_items",
    *(f"has_{f}" for f in TURNOUT_FIELDS),
    "data_status",
)


def render_csv(report: CompletenessReport) -> str:
    """Satu baris per wilayah per kontestasi, untuk dibuka di Excel.

    Titik koma dan BOM UTF-8: Excel berlokal Indonesia memakai titik koma sebagai
    pemisah daftar dan baru membaca huruf non-ASCII dengan benar bila ada BOM.
    Pembaca CSV proyek ini menerima keduanya.
    """
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for d in report.details:
        writer.writerow(
            [
                d.election_type.value,
                d.election_year,
                d.region.level.value,
                d.region.code,
                d.region.name,
                d.coverage.value,
                ", ".join(d.missing_items),
                *("ya" if f in d.turnout_fields else "tidak" for f in TURNOUT_FIELDS),
                ", ".join(sorted(s.value for s in d.statuses)),
            ]
        )
    return buffer.getvalue()
