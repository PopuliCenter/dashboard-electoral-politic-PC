"""Seed data referensi ke database sungguhan (T2.5).

Setiap test berjalan di transaksi yang di-rollback, jadi data fiktif tidak
pernah tersimpan (aturan data 2). Database pengembangan mungkin sudah berisi data
referensi asli; karena itu test di sini memeriksa keadaan akhir dan perubahan
yang dilaporkan, bukan jumlah baris absolut di tabel.
"""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, CandidatePair, Election, Party
from app.models.enums import ElectionType
from app.seed.apply import apply_reference_data
from app.seed.reference import load_reference_data
from tests.reference_fixtures import partai, partai_fiktif, tulis_referensi

pytestmark = pytest.mark.integration


async def _partai(session: AsyncSession, kode: str) -> Party:
    party = await session.scalar(select(Party).where(Party.party_code == kode))
    assert party is not None, kode
    return party


async def test_seed_menulis_partai_dengan_keikutsertaan_yang_benar(
    session: AsyncSession, tmp_path: Path
) -> None:
    await apply_reference_data(session, load_reference_data(tulis_referensi(tmp_path)))

    a = await _partai(session, "UJI_A")
    assert (a.contested_2019, a.ballot_number_2019) == (True, 901)
    assert (a.contested_2024, a.ballot_number_2024) == (True, 901)

    b = await _partai(session, "UJI_B")
    assert (b.contested_2019, b.contested_2024, b.ballot_number_2024) == (True, False, None)

    c = await _partai(session, "UJI_C")
    assert (c.contested_2019, c.ballot_number_2019, c.contested_2024) == (False, None, True)


async def test_seed_menulis_enam_kontestasi_dan_paslon(
    session: AsyncSession, tmp_path: Path
) -> None:
    await apply_reference_data(session, load_reference_data(tulis_referensi(tmp_path)))

    elections = (
        await session.scalars(select(Election).where(Election.election_year.in_((2019, 2024))))
    ).all()
    assert {(e.election_type, e.election_year) for e in elections} == {
        (t, y) for t in ElectionType for y in (2019, 2024)
    }
    assert {e.election_name for e in elections} >= {"Pemilu Uji Presiden 2019"}

    pilpres_2024 = next(
        e
        for e in elections
        if e.election_type is ElectionType.PRESIDENTIAL and e.election_year == 2024
    )
    pairs = (
        await session.scalars(
            select(CandidatePair).where(CandidatePair.election_id == pilpres_2024.id)
        )
    ).all()
    by_number = {p.pair_number: p for p in pairs}
    assert by_number[1].president_name == "Calon Uji 2024-1"
    assert by_number[2].vice_president_name == "Wakil Uji 2024-2"


async def test_seed_idempoten(session: AsyncSession, tmp_path: Path) -> None:
    """Jalan kedua dengan berkas yang sama tidak membuat atau mengubah apa pun."""
    data = load_reference_data(tulis_referensi(tmp_path))
    await apply_reference_data(session, data)
    kedua = await apply_reference_data(session, data)

    assert sum(kedua.created.values()) == 0
    assert sum(kedua.updated.values()) == 0
    assert kedua.unchanged == {"elections": 6, "parties": 3, "candidate_pairs": 4}
    assert kedua.changes == []


async def test_koreksi_nama_partai_tercatat_sebagai_perubahan(
    session: AsyncSession, tmp_path: Path
) -> None:
    await apply_reference_data(session, load_reference_data(tulis_referensi(tmp_path / "v1")))

    baris = partai_fiktif()
    baris[0]["party_name"] = "Partai A Baru"
    laporan = await apply_reference_data(
        session, load_reference_data(tulis_referensi(tmp_path / "v2", parties=baris))
    )

    assert laporan.updated["parties"] == 1
    assert laporan.changes == ["partai UJI_A diubah: party_name"]
    assert (await _partai(session, "UJI_A")).party_name == "Partai A Baru"


async def test_koreksi_yang_menukar_nomor_urut_dua_partai_berhasil(
    session: AsyncSession, tmp_path: Path
) -> None:
    """Tanpa keunikan yang ditunda, koreksi seperti ini tertolak di tengah jalan."""
    await apply_reference_data(session, load_reference_data(tulis_referensi(tmp_path / "v1")))

    tertukar = [
        partai("UJI_A", "Partai A", nomor_2019=902, nomor_2024=901),
        partai("UJI_B", "Partai B", nomor_2019=901),
        partai("UJI_C", "Partai C", nomor_2024=903),
    ]
    await apply_reference_data(
        session, load_reference_data(tulis_referensi(tmp_path / "v2", parties=tertukar))
    )

    assert (await _partai(session, "UJI_A")).ballot_number_2019 == 902
    assert (await _partai(session, "UJI_B")).ballot_number_2019 == 901


async def test_partai_berhenti_ikut_pemilu_dikoreksi_tanpa_melanggar_check(
    session: AsyncSession, tmp_path: Path
) -> None:
    """contested dan nomor urut berubah dalam satu UPDATE, jadi CHECK tetap terpenuhi."""
    await apply_reference_data(session, load_reference_data(tulis_referensi(tmp_path / "v1")))

    baris = partai_fiktif()
    baris[0] = partai("UJI_A", "Partai A", nomor_2019=901)
    await apply_reference_data(
        session, load_reference_data(tulis_referensi(tmp_path / "v2", parties=baris))
    )

    a = await _partai(session, "UJI_A")
    assert (a.contested_2024, a.ballot_number_2024) == (False, None)


async def test_partai_di_database_yang_tidak_ada_di_csv_tidak_dihapus(
    session: AsyncSession, tmp_path: Path
) -> None:
    yatim = Party(
        party_code="UJI_YATIM",
        party_name="Partai Uji Yatim",
        contested_2019=True,
        ballot_number_2019=950,
    )
    session.add(yatim)
    await session.flush()

    laporan = await apply_reference_data(session, load_reference_data(tulis_referensi(tmp_path)))

    assert any("UJI_YATIM" in w and "tidak dihapus" in w for w in laporan.warnings)
    assert await session.get(Party, yatim.id) is not None


async def test_nomor_urut_yang_dipakai_partai_di_luar_csv_ditolak_database(
    session: AsyncSession, tmp_path: Path
) -> None:
    """Partai yang tidak ada di CSV masih memegang nomornya; tabrakan harus gagal keras."""
    session.add(
        Party(
            party_code="UJI_PEMEGANG",
            party_name="Partai Uji Pemegang Nomor",
            contested_2019=True,
            ballot_number_2019=901,
        )
    )
    await session.flush()

    with pytest.raises(IntegrityError):
        await apply_reference_data(session, load_reference_data(tulis_referensi(tmp_path)))


async def test_setiap_seed_tercatat_di_audit_log_dengan_checksum(
    session: AsyncSession, tmp_path: Path
) -> None:
    data = load_reference_data(tulis_referensi(tmp_path))
    await apply_reference_data(session, data)

    log = (
        await session.scalars(
            select(AuditLog)
            .where(AuditLog.action == "seed_reference_data")
            .order_by(AuditLog.created_at.desc())
        )
    ).first()
    assert log is not None
    assert log.entity_type == "reference_data"
    assert log.payload is not None
    assert log.payload["checksums"] == data.checksums
    assert log.payload["unverified_rows"] == 13
