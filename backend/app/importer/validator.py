"""Validator format impor baku (T3.1).

Murni: tidak menyentuh database, hanya membaca `ReferenceCatalog`. Semua
kesalahan dikumpulkan dan dilaporkan sekaligus dengan nama berkas dan nomor
baris, supaya satu kali jalan cukup untuk melihat semua yang harus dibetulkan.

Yang diperiksa di sini (SDD 12.4):

- kolom sesuai salah satu dari tiga jenis berkas;
- satu berkas hanya satu kontestasi dan satu `data_status`;
- kontestasi ada di database; jenis berkas cocok dengan jenis kontestasi;
- kode wilayah berformat Kemendagri dan berlaku pada hari pemungutan suara;
- partai ikut pemilu tahun itu, paslon ada pada tahun itu;
- angka bilangan bulat tidak negatif, tanpa pemisah ribuan;
- tidak ada baris ganda.

Yang TIDAK diperiksa di sini: kecocokan total dengan rekapitulasi resmi (T3.3)
dan kelengkapan wilayah atau partai (T3.5). Angka partisipasi yang tidak saling
cocok hanya menjadi peringatan; rekapitulasi resmi kadang memang begitu, dan
rekonsiliasi yang melaporkannya, bukan validator yang menyembunyikannya.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from app.core.csv_files import check_columns, read_csv
from app.importer.catalog import ElectionKey, ReferenceCatalog
from app.importer.format import COLUMNS, LABEL, MARKER_COLUMNS, TURNOUT_FIELDS, RecordKind
from app.models.enums import DataStatus, ElectionType

REGION_CODE_PATTERN = re.compile(r"^\d{2}(\.\d{2}(\.\d{2})?)?$")

# Berapa nomor baris yang disebut saat meringkas masalah yang berulang.
MAX_LINES_LISTED = 5


@dataclass(frozen=True)
class PartyVote:
    line: int
    region_code: str
    party_code: str
    vote_count: int


@dataclass(frozen=True)
class CandidateVote:
    line: int
    region_code: str
    pair_number: int
    vote_count: int


@dataclass(frozen=True)
class Turnout:
    line: int
    region_code: str
    # None berarti angka itu tidak tersedia di dokumen sumber (aturan data 1).
    registered_voters: int | None
    voters_turned_out: int | None
    valid_votes: int | None
    invalid_votes: int | None


Record = PartyVote | CandidateVote | Turnout


@dataclass
class ValidationReport:
    file_name: str
    checksum: str | None = None
    kind: RecordKind | None = None
    election: ElectionKey | None = None
    data_status: DataStatus | None = None
    records: list[Record] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------- #
# Pembantu per sel
# --------------------------------------------------------------------------- #


class _Row:
    def __init__(self, file: str, line: int, data: dict[str, str], errors: list[str]) -> None:
        self.file = file
        self.line = line
        self.data = data
        self.errors = errors

    def error(self, message: str) -> None:
        self.errors.append(f"{self.file}:{self.line}: {message}")

    def count(self, column: str, *, required: bool) -> int | None:
        """Bilangan bulat >= 0. Kosong berarti tidak tersedia (bila boleh)."""
        value = self.data.get(column, "")
        if not value:
            if required:
                self.error(
                    f"{column} kosong. Bila angkanya tidak ada di dokumen sumber, "
                    "hapus barisnya; jangan diisi perkiraan"
                )
            return None
        if value.isdigit():
            return int(value)
        if value.startswith("-") and value[1:].isdigit():
            self.error(f"{column} tidak boleh negatif ({value})")
        elif re.fullmatch(r"\d{1,3}([.,]\d{3})+", value):
            digits = re.sub(r"[.,]", "", value)
            self.error(f"{column} {value!r}: tulis tanpa pemisah ribuan, yaitu {digits}")
        elif re.fullmatch(r"\d+[.,]\d+", value):
            self.error(f"{column} {value!r} harus bilangan bulat, bukan desimal")
        else:
            self.error(f"{column} {value!r} bukan bilangan bulat")
        return None


def _lines(lines: Iterable[int]) -> str:
    listed = sorted(lines)
    text = ", ".join(map(str, listed[:MAX_LINES_LISTED]))
    if len(listed) > MAX_LINES_LISTED:
        text += f", dan {len(listed) - MAX_LINES_LISTED} lainnya"
    return text


# --------------------------------------------------------------------------- #
# Tahap 1: jenis berkas
# --------------------------------------------------------------------------- #


def detect_kind(name: str, columns: tuple[str, ...], errors: list[str]) -> RecordKind | None:
    found = [kind for kind, marker in MARKER_COLUMNS.items() if marker in columns]
    if len(found) > 1:
        errors.append(
            f"{name}: berkas mencampur beberapa jenis data "
            f"({', '.join(LABEL[k] for k in found)}); pisahkan ke berkas sendiri-sendiri"
        )
        return None
    if not found:
        markers = ", ".join(MARKER_COLUMNS.values())
        errors.append(
            f"{name}: jenis berkas tidak dikenali; harus punya salah satu kolom {markers} "
            "(lihat docs/format-impor.md)"
        )
        return None
    kind = found[0]
    if not check_columns(name, columns, COLUMNS[kind], errors):
        return None
    return kind


# --------------------------------------------------------------------------- #
# Tahap 2: kontestasi dan status, harus seragam satu berkas
# --------------------------------------------------------------------------- #


def _uniform_election(
    report: ValidationReport,
    rows: tuple[tuple[int, dict[str, str]], ...],
    catalog: ReferenceCatalog,
) -> None:
    valid_types = {t.value for t in ElectionType}
    valid_statuses = {s.value for s in DataStatus}
    elections: dict[tuple[str, str], list[int]] = {}
    statuses: dict[str, list[int]] = {}
    for line, data in rows:
        elections.setdefault((data["election_type"], data["election_year"]), []).append(line)
        statuses.setdefault(data["data_status"], []).append(line)

    name = report.file_name
    if len(elections) > 1:
        detail = "; ".join(
            f"{t or '(kosong)'} {y or '(kosong)'} di baris {_lines(ls)}"
            for (t, y), ls in elections.items()
        )
        report.errors.append(
            f"{name}: satu berkas hanya boleh satu kontestasi, ditemukan {len(elections)}: "
            f"{detail}"
        )
    elif elections:
        (raw_type, raw_year), _ = next(iter(elections.items()))
        if raw_type not in valid_types:
            report.errors.append(
                f"{name}: election_type {raw_type!r} tidak dikenal; pilih salah satu: "
                f"{', '.join(sorted(valid_types))}"
            )
        elif not raw_year.isdigit():
            report.errors.append(f"{name}: election_year {raw_year!r} harus tahun, misal 2024")
        else:
            key = (ElectionType(raw_type), int(raw_year))
            if key not in catalog.elections:
                report.errors.append(
                    f"{name}: kontestasi {raw_type} {raw_year} tidak ada di database; "
                    "jalankan seed data referensi lebih dulu (make seed)"
                )
            else:
                report.election = key

    if len(statuses) > 1:
        detail = "; ".join(f"{s or '(kosong)'} di baris {_lines(ls)}" for s, ls in statuses.items())
        report.errors.append(
            f"{name}: satu berkas hanya boleh satu data_status, ditemukan {len(statuses)}: "
            f"{detail}. Pisahkan data resmi dan tidak resmi ke berkas berbeda"
        )
    elif statuses:
        raw_status = next(iter(statuses))
        if raw_status not in valid_statuses:
            report.errors.append(
                f"{name}: data_status {raw_status!r} tidak dikenal; pilih salah satu: "
                f"{', '.join(sorted(valid_statuses))}"
            )
        else:
            report.data_status = DataStatus(raw_status)
            if report.data_status is DataStatus.UNOFFICIAL:
                report.warnings.append(
                    f"{name}: data tidak resmi (unofficial). Boleh tidaknya data Sirekap/Situng "
                    "ditampilkan masih keputusan terbuka (docs/decisions.md)"
                )


def _kind_matches_election(report: ValidationReport) -> None:
    if report.kind is None or report.election is None:
        return
    election_type, year = report.election
    presidential = election_type is ElectionType.PRESIDENTIAL
    if report.kind is RecordKind.CANDIDATE_VOTES and not presidential:
        report.errors.append(
            f"{report.file_name}: suara pasangan calon hanya untuk Pilpres, bukan "
            f"{election_type.value} {year}"
        )
    if report.kind is RecordKind.PARTY_VOTES and presidential:
        report.errors.append(
            f"{report.file_name}: Pilpres {year} tidak punya suara partai; "
            "gunakan berkas suara pasangan calon (kolom pair_number)"
        )


# --------------------------------------------------------------------------- #
# Tahap 3: per baris
# --------------------------------------------------------------------------- #


def _region(r: _Row, report: ValidationReport, catalog: ReferenceCatalog) -> str | None:
    code = r.data["region_code"]
    if not code:
        r.error("region_code wajib diisi")
        return None
    if not REGION_CODE_PATTERN.match(code):
        r.error(
            f"region_code {code!r} bukan format kode Kemendagri "
            "(misal 32, 32.04, atau 32.04.05; nol di depan jangan hilang)"
        )
        return None
    if report.election is not None:
        election_type, year = report.election
        if code not in catalog.regions.get(report.election, {}):
            r.error(
                f"region_code {code} tidak dikenal atau tidak berlaku pada Pemilu {year} "
                f"({election_type.value})"
            )
            return None
    return code


def _parse_rows(
    report: ValidationReport,
    rows: tuple[tuple[int, dict[str, str]], ...],
    catalog: ReferenceCatalog,
) -> None:
    year = report.election[1] if report.election else None
    unknown_parties: dict[str, list[int]] = {}
    absent_parties: dict[str, list[int]] = {}

    for line, data in rows:
        r = _Row(report.file_name, line, data, report.errors)
        region = _region(r, report, catalog)

        if report.kind is RecordKind.PARTY_VOTES:
            party = data["party_code"]
            if not party:
                r.error("party_code wajib diisi")
            elif party not in catalog.party_years:
                unknown_parties.setdefault(party, []).append(line)
                party = ""
            elif year is not None and year not in catalog.party_years[party]:
                absent_parties.setdefault(party, []).append(line)
                party = ""
            votes = r.count("vote_count", required=True)
            if region and party and votes is not None:
                report.records.append(PartyVote(line, region, party, votes))

        elif report.kind is RecordKind.CANDIDATE_VOTES:
            raw_pair = data["pair_number"]
            pair: int | None = None
            if not raw_pair.isdigit() or int(raw_pair) == 0:
                r.error(f"pair_number {raw_pair!r} harus nomor urut paslon (1, 2, ...)")
            elif year is not None and (year, int(raw_pair)) not in catalog.candidate_pairs:
                r.error(f"pasangan calon nomor {raw_pair} tidak ada di Pilpres {year}")
            else:
                pair = int(raw_pair)
            votes = r.count("vote_count", required=True)
            if region and pair is not None and votes is not None:
                report.records.append(CandidateVote(line, region, pair, votes))

        elif report.kind is RecordKind.TURNOUT:
            counts = {f: r.count(f, required=False) for f in TURNOUT_FIELDS}
            if all(not data[f] for f in TURNOUT_FIELDS):
                r.error("semua angka partisipasi kosong; hapus barisnya bila memang tidak tersedia")
            elif region and all(counts[f] is not None or not data[f] for f in TURNOUT_FIELDS):
                report.records.append(
                    Turnout(
                        line,
                        region,
                        registered_voters=counts["registered_voters"],
                        voters_turned_out=counts["voters_turned_out"],
                        valid_votes=counts["valid_votes"],
                        invalid_votes=counts["invalid_votes"],
                    )
                )

    name = report.file_name
    for party, lines in unknown_parties.items():
        report.errors.append(
            f"{name}: party_code {party!r} tidak dikenal (baris {_lines(lines)}); "
            "lihat data/reference/parties.csv"
        )
    for party, lines in absent_parties.items():
        report.errors.append(
            f"{name}: partai {party} tidak ikut Pemilu {year} (baris {_lines(lines)})"
        )


def _no_duplicates(report: ValidationReport) -> None:
    seen: dict[tuple[str, object], list[int]] = {}
    for record in report.records:
        key: tuple[str, object]
        if isinstance(record, PartyVote):
            key = (record.region_code, record.party_code)
        elif isinstance(record, CandidateVote):
            key = (record.region_code, record.pair_number)
        else:
            key = (record.region_code, None)
        seen.setdefault(key, []).append(record.line)
    for (region, item), lines in seen.items():
        if len(lines) > 1:
            what = f"wilayah {region}" + (f" dan {item}" if item is not None else "")
            report.errors.append(
                f"{report.file_name}: {what} muncul lebih dari sekali (baris {_lines(lines)})"
            )


def _turnout_warnings(report: ValidationReport) -> None:
    for record in report.records:
        if not isinstance(record, Turnout):
            continue
        where = f"{report.file_name}:{record.line}: wilayah {record.region_code}"
        if (
            record.valid_votes is not None
            and record.invalid_votes is not None
            and record.voters_turned_out is not None
            and record.valid_votes + record.invalid_votes != record.voters_turned_out
        ):
            report.warnings.append(
                f"{where}: suara sah + tidak sah ({record.valid_votes + record.invalid_votes}) "
                f"tidak sama dengan pengguna hak pilih ({record.voters_turned_out}); "
                "periksa dokumen sumber"
            )
        if (
            record.voters_turned_out is not None
            and record.registered_voters is not None
            and record.voters_turned_out > record.registered_voters
        ):
            report.warnings.append(
                f"{where}: pengguna hak pilih ({record.voters_turned_out}) melebihi DPT "
                f"({record.registered_voters}); bisa wajar karena DPTb dan DPK, periksa "
                "dokumen sumber"
            )


# --------------------------------------------------------------------------- #
# API publik
# --------------------------------------------------------------------------- #


def validate_rows(
    name: str,
    columns: tuple[str, ...],
    rows: tuple[tuple[int, dict[str, str]], ...],
    catalog: ReferenceCatalog,
    *,
    checksum: str | None = None,
) -> ValidationReport:
    """Validasi baris yang sudah dibaca. Dipakai juga oleh unggahan XLSX (T5.2)."""
    report = ValidationReport(file_name=name, checksum=checksum)
    report.kind = detect_kind(name, columns, report.errors)
    if report.kind is None:
        return report
    if not rows:
        report.errors.append(f"{name}: tidak ada baris data")
        return report

    _uniform_election(report, rows, catalog)
    _kind_matches_election(report)
    if report.errors:
        # Tanpa kontestasi yang jelas, pemeriksaan per baris hanya menghasilkan
        # rentetan galat turunan yang menyesatkan.
        report.records.clear()
        return report

    _parse_rows(report, rows, catalog)
    _no_duplicates(report)
    _turnout_warnings(report)
    if report.errors:
        report.records.clear()
    return report


def validate_file(path: Path, catalog: ReferenceCatalog) -> ValidationReport:
    errors: list[str] = []
    table = read_csv(path, errors)
    if table is None:
        return ValidationReport(file_name=path.name, errors=errors)
    report = validate_rows(table.name, table.columns, table.rows, catalog, checksum=table.checksum)
    report.errors[:0] = errors
    if report.errors:
        report.records.clear()
    return report
