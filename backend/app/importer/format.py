"""Format impor baku (T3.1). Penjelasan untuk manusia ada di docs/format-impor.md.

Ada tiga jenis berkas, dikenali dari kolomnya:

- `party_votes`: suara partai per wilayah (DPR RI, DPRD Provinsi).
- `candidate_votes`: suara pasangan calon per wilayah (Pilpres saja).
- `turnout`: DPT, pengguna hak pilih, suara sah, dan suara tidak sah per wilayah.

Satu berkas = satu kontestasi = satu `data_status`. Itu yang nanti menjadi satu
versi dataset dengan satu sumber (T3.4), dan mencegah kontestasi tercampur
(aturan data 3).
"""

from enum import StrEnum


class RecordKind(StrEnum):
    PARTY_VOTES = "party_votes"
    CANDIDATE_VOTES = "candidate_votes"
    TURNOUT = "turnout"


COMMON_COLUMNS = ("election_type", "election_year", "region_code")

TURNOUT_FIELDS = ("registered_voters", "voters_turned_out", "valid_votes", "invalid_votes")

COLUMNS: dict[RecordKind, tuple[str, ...]] = {
    RecordKind.PARTY_VOTES: (*COMMON_COLUMNS, "party_code", "vote_count", "data_status"),
    RecordKind.CANDIDATE_VOTES: (*COMMON_COLUMNS, "pair_number", "vote_count", "data_status"),
    RecordKind.TURNOUT: (*COMMON_COLUMNS, *TURNOUT_FIELDS, "data_status"),
}

# Kolom yang hanya ada di satu jenis berkas; dipakai untuk mengenali jenisnya.
MARKER_COLUMNS: dict[RecordKind, str] = {
    RecordKind.PARTY_VOTES: "party_code",
    RecordKind.CANDIDATE_VOTES: "pair_number",
    RecordKind.TURNOUT: "registered_voters",
}

LABEL: dict[RecordKind, str] = {
    RecordKind.PARTY_VOTES: "suara partai",
    RecordKind.CANDIDATE_VOTES: "suara pasangan calon",
    RecordKind.TURNOUT: "partisipasi",
}
