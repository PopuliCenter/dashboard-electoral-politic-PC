"""Membaca dan memvalidasi berkas data referensi di data/reference/ (T2.5).

Modul ini murni: tidak menyentuh database. Kesalahan dikumpulkan lalu
dilaporkan sekaligus dengan nama berkas dan nomor baris, supaya peneliti yang
membetulkan CSV melihat semua masalah dalam satu kali jalan. Pemeriksaan lintas
berkas (kelengkapan enam kontestasi, tanggal serentak, nomor urut paslon) baru
dijalankan setelah ketiga berkas bersih, supaya satu salah ketik tidak memicu
rentetan galat turunan yang menyesatkan.

Berkas biasanya disunting di Excel; pembacaannya (BOM, pemisah titik koma) ada
di app.core.csv_files dan dipakai bersama validator impor T3.1.
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.core.csv_files import check_columns, parse_whole_number, read_csv
from app.models.enums import ElectionType

# Terikat ke kolom contested_<tahun> dan ballot_number_<tahun> di tabel parties.
# Menambah tahun berarti menambah kolom lewat migrasi, bukan hanya mengubah ini.
SUPPORTED_YEARS: tuple[int, ...] = (2019, 2024)

PARTIES_FILE = "parties.csv"
ELECTIONS_FILE = "elections.csv"
CANDIDATE_PAIRS_FILE = "candidate_pairs.csv"

PARTY_COLUMNS = (
    "party_code",
    "party_name",
    "party_abbreviation",
    *(f"ballot_number_{year}" for year in SUPPORTED_YEARS),
    *(f"source_{year}" for year in SUPPORTED_YEARS),
    "verified_by",
    "notes",
)
ELECTION_COLUMNS = (
    "election_type",
    "election_year",
    "election_date",
    "election_name",
    "source",
    "verified_by",
)
CANDIDATE_PAIR_COLUMNS = (
    "election_year",
    "pair_number",
    "president_name",
    "vice_president_name",
    "source",
    "verified_by",
)

PARTY_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,29}$")

# Batas panjang mengikuti kolom database, supaya ditolak di sini dengan pesan
# yang jelas, bukan oleh database dengan galat yang membingungkan.
MAX_LEN = {
    "party_code": 30,
    "party_name": 150,
    "party_abbreviation": 30,
    "election_name": 150,
    "president_name": 150,
    "vice_president_name": 150,
    "source": 500,
    "verified_by": 100,
    "notes": 500,
}


class ReferenceDataError(Exception):
    """Data referensi tidak lolos validasi. `errors` berisi semua masalah."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        daftar = "\n".join(f"  - {error}" for error in errors)
        super().__init__(f"{len(errors)} kesalahan pada data referensi:\n{daftar}")


@dataclass(frozen=True)
class PartyRow:
    line: int
    party_code: str
    party_name: str
    party_abbreviation: str
    ballot_numbers: dict[int, int | None]
    sources: dict[int, str | None]
    verified_by: str | None
    notes: str | None

    def contested(self, year: int) -> bool:
        return self.ballot_numbers[year] is not None


@dataclass(frozen=True)
class ElectionRow:
    line: int
    election_type: ElectionType
    election_year: int
    election_date: date
    election_name: str
    source: str
    verified_by: str | None


@dataclass(frozen=True)
class CandidatePairRow:
    line: int
    election_year: int
    pair_number: int
    president_name: str
    vice_president_name: str
    source: str
    verified_by: str | None


@dataclass(frozen=True)
class ReferenceData:
    parties: tuple[PartyRow, ...]
    elections: tuple[ElectionRow, ...]
    candidate_pairs: tuple[CandidatePairRow, ...]
    checksums: dict[str, str]


# --------------------------------------------------------------------------- #
# Pembacaan CSV
# --------------------------------------------------------------------------- #


def _read_csv(
    path: Path, expected: tuple[str, ...], errors: list[str]
) -> tuple[list[tuple[int, dict[str, str]]], str | None]:
    """Kembalikan (baris, checksum). Baris kosong dilewati."""
    table = read_csv(path, errors)
    if table is None:
        return [], None
    if not check_columns(table.name, table.columns, expected, errors):
        return [], table.checksum
    return list(table.rows), table.checksum


class _Row:
    """Pembantu membaca satu baris dengan pesan galat berlokasi."""

    def __init__(self, file: str, line: int, data: dict[str, str], errors: list[str]) -> None:
        self.file = file
        self.line = line
        self.data = data
        self.errors = errors

    def error(self, message: str) -> None:
        self.errors.append(f"{self.file}:{self.line}: {message}")

    def text(self, column: str, *, required: bool = True) -> str | None:
        value = self.data.get(column, "")
        if not value:
            if required:
                self.error(f"{column} wajib diisi")
            return None
        limit = MAX_LEN.get(column) or MAX_LEN.get(column.rsplit("_", 1)[0])
        if limit and len(value) > limit:
            self.error(f"{column} lebih dari {limit} karakter")
        return value

    def integer(self, column: str, *, required: bool = True) -> int | None:
        value = self.data.get(column, "")
        if not value:
            if required:
                self.error(f"{column} wajib diisi")
            return None
        number = parse_whole_number(value)
        if isinstance(number, str):
            self.error(f"{column} harus bilangan bulat positif: {number}")
            return None
        if number <= 0:
            self.error(f"{column} harus lebih dari 0")
            return None
        return number


# --------------------------------------------------------------------------- #
# Validasi per berkas
# --------------------------------------------------------------------------- #


def _parse_parties(rows: list[tuple[int, dict[str, str]]], errors: list[str]) -> list[PartyRow]:
    parties: list[PartyRow] = []
    for line, data in rows:
        r = _Row(PARTIES_FILE, line, data, errors)
        code = r.text("party_code")
        if code and not PARTY_CODE_PATTERN.match(code):
            r.error(
                f"party_code {code!r} harus huruf kapital, angka, atau garis bawah, diawali huruf"
            )
        name = r.text("party_name")
        abbreviation = r.text("party_abbreviation")

        numbers: dict[int, int | None] = {}
        sources: dict[int, str | None] = {}
        for year in SUPPORTED_YEARS:
            numbers[year] = r.integer(f"ballot_number_{year}", required=False)
            sources[year] = r.text(f"source_{year}", required=False)
            raw_number = data.get(f"ballot_number_{year}", "")
            if raw_number and not sources[year]:
                r.error(f"ikut pemilu {year} tetapi source_{year} kosong")
            if sources[year] and not raw_number:
                r.error(f"source_{year} terisi tetapi ballot_number_{year} kosong")

        if all(not data.get(f"ballot_number_{y}", "") for y in SUPPORTED_YEARS):
            r.error("partai harus punya nomor urut minimal di satu pemilu")

        verified_by = r.text("verified_by", required=False)
        notes = r.text("notes", required=False)
        if code and name and abbreviation:
            parties.append(
                PartyRow(line, code, name, abbreviation, numbers, sources, verified_by, notes)
            )

    _no_duplicates(errors, PARTIES_FILE, "party_code", [(p.line, p.party_code) for p in parties])
    _no_duplicates(
        errors,
        PARTIES_FILE,
        "party_name",
        [(p.line, p.party_name.casefold()) for p in parties],
    )
    for year in SUPPORTED_YEARS:
        _no_duplicates(
            errors,
            PARTIES_FILE,
            f"ballot_number_{year}",
            [(p.line, n) for p in parties if (n := p.ballot_numbers[year]) is not None],
        )
        if parties and not any(p.contested(year) for p in parties):
            errors.append(f"{PARTIES_FILE}: tidak ada satu pun partai yang ikut pemilu {year}")
    return parties


def _parse_elections(
    rows: list[tuple[int, dict[str, str]]], errors: list[str]
) -> list[ElectionRow]:
    elections: list[ElectionRow] = []
    valid_types = {t.value for t in ElectionType}
    for line, data in rows:
        r = _Row(ELECTIONS_FILE, line, data, errors)
        raw_type = r.text("election_type")
        election_type: ElectionType | None = None
        if raw_type is not None:
            if raw_type in valid_types:
                election_type = ElectionType(raw_type)
            else:
                r.error(
                    f"election_type {raw_type!r} tidak dikenal; pilih salah satu: "
                    f"{', '.join(sorted(valid_types))}"
                )

        year = r.integer("election_year")
        if year is not None and year not in SUPPORTED_YEARS:
            r.error(
                f"election_year {year} di luar cakupan fase 1 "
                f"({', '.join(map(str, SUPPORTED_YEARS))})"
            )

        raw_date = r.text("election_date")
        election_date: date | None = None
        if raw_date is not None:
            try:
                election_date = date.fromisoformat(raw_date)
            except ValueError:
                r.error(f"election_date {raw_date!r} harus berformat YYYY-MM-DD")
        if election_date and year and election_date.year != year:
            r.error(f"election_date {election_date} tidak berada di tahun {year}")

        name = r.text("election_name")
        source = r.text("source")
        verified_by = r.text("verified_by", required=False)
        if election_type and year and election_date and name and source:
            elections.append(
                ElectionRow(line, election_type, year, election_date, name, source, verified_by)
            )

    _no_duplicates(
        errors,
        ELECTIONS_FILE,
        "kombinasi election_type dan election_year",
        [(e.line, (e.election_type.value, e.election_year)) for e in elections],
    )
    return elections


def _parse_candidate_pairs(
    rows: list[tuple[int, dict[str, str]]], errors: list[str]
) -> list[CandidatePairRow]:
    pairs: list[CandidatePairRow] = []
    for line, data in rows:
        r = _Row(CANDIDATE_PAIRS_FILE, line, data, errors)
        year = r.integer("election_year")
        number = r.integer("pair_number")
        president = r.text("president_name")
        vice = r.text("vice_president_name")
        source = r.text("source")
        verified_by = r.text("verified_by", required=False)
        if year and number and president and vice and source:
            pairs.append(CandidatePairRow(line, year, number, president, vice, source, verified_by))
    _no_duplicates(
        errors,
        CANDIDATE_PAIRS_FILE,
        "kombinasi election_year dan pair_number",
        [(p.line, (p.election_year, p.pair_number)) for p in pairs],
    )
    return pairs


def _no_duplicates(
    errors: list[str], file: str, what: str, keyed: list[tuple[int, object]]
) -> None:
    lines_by_key: dict[object, list[int]] = {}
    for line, key in keyed:
        lines_by_key.setdefault(key, []).append(line)
    for key, lines in lines_by_key.items():
        if len(lines) > 1:
            errors.append(
                f"{file}: {what} {key!r} muncul lebih dari sekali "
                f"(baris {', '.join(map(str, lines))})"
            )


# --------------------------------------------------------------------------- #
# Validasi lintas berkas
# --------------------------------------------------------------------------- #


def _cross_checks(
    elections: list[ElectionRow], pairs: list[CandidatePairRow], errors: list[str]
) -> None:
    present = {(e.election_type, e.election_year) for e in elections}
    for year in SUPPORTED_YEARS:
        for election_type in ElectionType:
            if (election_type, year) not in present:
                errors.append(
                    f"{ELECTIONS_FILE}: kontestasi {election_type.value} {year} tidak ada; "
                    f"fase 1 butuh tepat {len(ElectionType) * len(SUPPORTED_YEARS)} kontestasi"
                )

        # Sejak 2019 Pemilu serentak: Pilpres, DPR RI, dan DPRD Provinsi pada hari
        # yang sama. Tanggal berbeda di tahun yang sama hampir pasti salah ketik.
        dates = {e.election_date for e in elections if e.election_year == year}
        if len(dates) > 1:
            errors.append(
                f"{ELECTIONS_FILE}: kontestasi tahun {year} punya tanggal berbeda "
                f"({', '.join(sorted(map(str, dates)))}); Pemilu {year} serentak dalam satu hari"
            )

        numbers = sorted(p.pair_number for p in pairs if p.election_year == year)
        if not numbers:
            errors.append(f"{CANDIDATE_PAIRS_FILE}: tidak ada pasangan calon untuk Pilpres {year}")
        elif numbers != list(range(1, len(numbers) + 1)):
            errors.append(
                f"{CANDIDATE_PAIRS_FILE}: nomor urut Pilpres {year} harus berurutan mulai 1, "
                f"ditemukan {numbers}"
            )

    presidential_years = {
        e.election_year for e in elections if e.election_type is ElectionType.PRESIDENTIAL
    }
    for p in pairs:
        if p.election_year in SUPPORTED_YEARS and p.election_year not in presidential_years:
            errors.append(
                f"{CANDIDATE_PAIRS_FILE}:{p.line}: tidak ada kontestasi Pilpres {p.election_year} "
                f"di {ELECTIONS_FILE}"
            )
        elif p.election_year not in SUPPORTED_YEARS:
            errors.append(
                f"{CANDIDATE_PAIRS_FILE}:{p.line}: election_year {p.election_year} di luar "
                f"cakupan fase 1"
            )


# --------------------------------------------------------------------------- #
# API publik
# --------------------------------------------------------------------------- #


def load_reference_data(directory: Path) -> ReferenceData:
    """Baca dan validasi ketiga berkas. Melempar ReferenceDataError bila ada masalah."""
    errors: list[str] = []
    party_rows, party_sum = _read_csv(directory / PARTIES_FILE, PARTY_COLUMNS, errors)
    election_rows, election_sum = _read_csv(directory / ELECTIONS_FILE, ELECTION_COLUMNS, errors)
    pair_rows, pair_sum = _read_csv(
        directory / CANDIDATE_PAIRS_FILE, CANDIDATE_PAIR_COLUMNS, errors
    )

    parties = _parse_parties(party_rows, errors)
    elections = _parse_elections(election_rows, errors)
    pairs = _parse_candidate_pairs(pair_rows, errors)
    if not errors:
        _cross_checks(elections, pairs, errors)

    if errors:
        raise ReferenceDataError(errors)

    checksums = {
        name: digest
        for name, digest in (
            (PARTIES_FILE, party_sum),
            (ELECTIONS_FILE, election_sum),
            (CANDIDATE_PAIRS_FILE, pair_sum),
        )
        if digest is not None
    }
    return ReferenceData(tuple(parties), tuple(elections), tuple(pairs), checksums)


def unverified_rows(data: ReferenceData) -> list[str]:
    """Lokasi baris yang belum diperiksa manusia terhadap dokumen KPU."""
    rows: list[str] = []
    rows += [f"{PARTIES_FILE}:{p.line}" for p in data.parties if not p.verified_by]
    rows += [f"{ELECTIONS_FILE}:{e.line}" for e in data.elections if not e.verified_by]
    rows += [f"{CANDIDATE_PAIRS_FILE}:{p.line}" for p in data.candidate_pairs if not p.verified_by]
    return rows


def check_verification(data: ReferenceData, app_env: str) -> list[str]:
    """Gerbang verifikasi manusia.

    Di produksi, setiap baris wajib punya `verified_by`: data referensi yang belum
    dicocokkan dengan dokumen KPU oleh peneliti tidak boleh masuk. Di lingkungan
    lain hanya menjadi peringatan. Mengembalikan daftar peringatan.
    """
    pending = unverified_rows(data)
    if not pending:
        return []
    if app_env == "production":
        raise ReferenceDataError(
            [
                f"{len(pending)} baris belum diverifikasi (kolom verified_by kosong); "
                "produksi hanya menerima data referensi yang sudah dicocokkan dengan "
                "dokumen KPU oleh peneliti",
                *(f"belum diverifikasi: {location}" for location in pending),
            ]
        )
    return [
        f"{len(pending)} baris belum diverifikasi (kolom verified_by kosong). "
        "Boleh di lingkungan pengembangan, akan ditolak di produksi."
    ]
