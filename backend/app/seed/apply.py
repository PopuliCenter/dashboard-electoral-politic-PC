"""Menulis data referensi yang sudah tervalidasi ke database (T2.5).

Prinsip:

- Idempoten. Kunci alami: `party_code`; (`election_type`, `election_year`);
  (`election_id`, `pair_number`). Menjalankan dua kali tidak menggandakan apa pun.
- Tidak pernah menghapus. Baris di database yang tidak ada di CSV dilaporkan
  sebagai peringatan; hasil pemilu bisa merujuk ke baris itu.
- Satu transaksi. Fungsi ini tidak melakukan commit; pemanggil yang memutuskan
  commit atau rollback (rollback dipakai untuk --dry-run dan oleh test).
- Setiap jalan tercatat di `audit_logs` beserta checksum berkas sumbernya.
"""

import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, CandidatePair, Election, Party
from app.models.enums import ElectionType
from app.seed.reference import SUPPORTED_YEARS, ReferenceData, unverified_rows

Entity = Literal["elections", "parties", "candidate_pairs"]
ENTITIES: tuple[Entity, ...] = ("elections", "parties", "candidate_pairs")

BALLOT_UNIQUE_CONSTRAINTS = tuple(f"uq_parties_ballot_number_{year}" for year in SUPPORTED_YEARS)


@dataclass
class SeedReport:
    created: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ENTITIES, 0))
    updated: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ENTITIES, 0))
    unchanged: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ENTITIES, 0))
    warnings: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)

    def as_payload(self) -> dict[str, object]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "warnings": self.warnings,
            "changes": self.changes,
        }


def _assign(obj: object, values: dict[str, object]) -> list[str]:
    """Set atribut yang berbeda saja; kembalikan nama kolom yang berubah."""
    changed = []
    for name, value in values.items():
        if getattr(obj, name) != value:
            setattr(obj, name, value)
            changed.append(name)
    return changed


async def _seed_elections(
    session: AsyncSession, data: ReferenceData, report: SeedReport
) -> dict[tuple[ElectionType, int], Election]:
    existing = {
        (e.election_type, e.election_year): e
        for e in (
            await session.scalars(
                select(Election).where(Election.election_year.in_(SUPPORTED_YEARS))
            )
        ).all()
    }
    for row in data.elections:
        key = (row.election_type, row.election_year)
        values: dict[str, object] = {
            "election_name": row.election_name,
            "election_date": row.election_date,
        }
        election = existing.get(key)
        if election is None:
            election = Election(
                election_type=row.election_type, election_year=row.election_year, **values
            )
            session.add(election)
            existing[key] = election
            report.created["elections"] += 1
            report.changes.append(f"kontestasi baru: {row.election_type.value} {row.election_year}")
        elif changed := _assign(election, values):
            report.updated["elections"] += 1
            report.changes.append(
                f"kontestasi {row.election_type.value} {row.election_year} diubah: "
                f"{', '.join(changed)}"
            )
        else:
            report.unchanged["elections"] += 1
    await session.flush()
    return existing


async def _seed_candidate_pairs(
    session: AsyncSession,
    data: ReferenceData,
    elections: dict[tuple[ElectionType, int], Election],
    report: SeedReport,
) -> None:
    presidential = {
        year: election
        for (election_type, year), election in elections.items()
        if election_type is ElectionType.PRESIDENTIAL
    }
    election_ids = [e.id for e in presidential.values()]
    existing = {
        (p.election_id, p.pair_number): p
        for p in (
            await session.scalars(
                select(CandidatePair).where(CandidatePair.election_id.in_(election_ids))
            )
        ).all()
    }
    seen: set[tuple[uuid.UUID, int]] = set()
    for row in data.candidate_pairs:
        election = presidential[row.election_year]
        key = (election.id, row.pair_number)
        seen.add(key)
        values: dict[str, object] = {
            "president_name": row.president_name,
            "vice_president_name": row.vice_president_name,
        }
        pair = existing.get(key)
        if pair is None:
            session.add(
                CandidatePair(election_id=election.id, pair_number=row.pair_number, **values)
            )
            report.created["candidate_pairs"] += 1
            report.changes.append(
                f"paslon baru: Pilpres {row.election_year} nomor {row.pair_number}"
            )
        elif changed := _assign(pair, values):
            report.updated["candidate_pairs"] += 1
            report.changes.append(
                f"paslon Pilpres {row.election_year} nomor {row.pair_number} diubah: "
                f"{', '.join(changed)}"
            )
        else:
            report.unchanged["candidate_pairs"] += 1

    year_of = {e.id: year for year, e in presidential.items()}
    for (election_id, number), _pair in sorted(existing.items(), key=lambda kv: kv[0][1]):
        if (election_id, number) not in seen:
            report.warnings.append(
                f"paslon Pilpres {year_of[election_id]} nomor {number} ada di database tetapi "
                "tidak di CSV; dibiarkan, tidak dihapus"
            )
    await session.flush()


async def _seed_parties(session: AsyncSession, data: ReferenceData, report: SeedReport) -> None:
    existing = {p.party_code: p for p in (await session.scalars(select(Party))).all()}
    for row in data.parties:
        values: dict[str, object] = {
            "party_name": row.party_name,
            "party_abbreviation": row.party_abbreviation,
        }
        for year in SUPPORTED_YEARS:
            values[f"contested_{year}"] = row.contested(year)
            values[f"ballot_number_{year}"] = row.ballot_numbers[year]

        party = existing.get(row.party_code)
        if party is None:
            session.add(Party(party_code=row.party_code, **values))
            report.created["parties"] += 1
            report.changes.append(f"partai baru: {row.party_code}")
        elif changed := _assign(party, values):
            report.updated["parties"] += 1
            report.changes.append(f"partai {row.party_code} diubah: {', '.join(changed)}")
        else:
            report.unchanged["parties"] += 1

    in_csv = {p.party_code for p in data.parties}
    for code in sorted(set(existing) - in_csv):
        report.warnings.append(
            f"partai {code} ada di database tetapi tidak di CSV; dibiarkan, tidak dihapus"
        )
    await session.flush()


async def apply_reference_data(
    session: AsyncSession, data: ReferenceData, *, actor_user_id: uuid.UUID | None = None
) -> SeedReport:
    """Upsert kontestasi, paslon, dan partai. Tidak melakukan commit."""
    report = SeedReport()

    # Keunikan nomor urut ditunda sampai akhir supaya koreksi yang menukar nomor
    # dua partai tidak tertolak di tengah jalan, lalu dipaksa diperiksa di sini,
    # bukan saat commit, supaya pelanggaran muncul dari fungsi ini.
    constraints = ", ".join(BALLOT_UNIQUE_CONSTRAINTS)
    await session.execute(text(f"SET CONSTRAINTS {constraints} DEFERRED"))

    elections = await _seed_elections(session, data, report)
    await _seed_candidate_pairs(session, data, elections, report)
    await _seed_parties(session, data, report)

    await session.execute(text(f"SET CONSTRAINTS {constraints} IMMEDIATE"))

    pending = unverified_rows(data)
    session.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action="seed_reference_data",
            entity_type="reference_data",
            payload={
                **report.as_payload(),
                "checksums": data.checksums,
                "unverified_rows": len(pending),
            },
        )
    )
    await session.flush()
    return report
