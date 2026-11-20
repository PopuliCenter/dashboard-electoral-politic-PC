"""nomor urut partai per pemilu

Revision ID: c4c10e7ad67f
Revises: 9b0b6025671e
Create Date: 2026-11-20 03:52:51.666480

Menambah nomor urut resmi KPU per pemilu ke `parties` (T2.5).

Ditulis tangan, bukan hasil autogenerate apa adanya: Alembic tidak mendeteksi
CHECK constraint yang ditambahkan ke tabel yang sudah ada, sehingga dua CHECK
di bawah tidak akan pernah muncul dari autogenerate dan `alembic check` juga
tidak akan menangkap bila keduanya hilang. Keberadaannya di database diuji di
tests/test_schema_db.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4c10e7ad67f"
down_revision: str | None = "9b0b6025671e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CHECK baru mewajibkan nomor urut untuk partai yang ikut pemilu. Pada saat
    # migrasi ini ditulis, tabel parties belum pernah diisi di lingkungan mana
    # pun (pengisian pertama adalah seed T2.5). Bila ternyata sudah ada isinya,
    # berhenti dengan pesan jelas daripada gagal di tengah dengan galat CHECK.
    bind = op.get_bind()
    jumlah = bind.execute(sa.text("SELECT count(*) FROM parties")).scalar_one()
    if jumlah:
        raise RuntimeError(
            f"parties sudah berisi {jumlah} baris tanpa nomor urut. Isi ballot_number_2019 "
            "dan ballot_number_2024 lebih dulu, atau kosongkan tabel, lalu ulangi migrasi."
        )

    op.add_column("parties", sa.Column("ballot_number_2019", sa.Integer(), nullable=True))
    op.add_column("parties", sa.Column("ballot_number_2024", sa.Integer(), nullable=True))

    # DEFERRABLE INITIALLY IMMEDIATE: berperilaku biasa, tetapi seed boleh menunda
    # pemeriksaan sampai akhir transaksi sehingga koreksi yang menukar nomor urut
    # dua partai tidak tertolak di tengah jalan.
    op.create_unique_constraint(
        "uq_parties_ballot_number_2019",
        "parties",
        ["ballot_number_2019"],
        deferrable=True,
        initially="IMMEDIATE",
    )
    op.create_unique_constraint(
        "uq_parties_ballot_number_2024",
        "parties",
        ["ballot_number_2024"],
        deferrable=True,
        initially="IMMEDIATE",
    )

    op.create_check_constraint(
        op.f("ck_parties_nomor_urut_2019_sesuai_keikutsertaan"),
        "parties",
        "(contested_2019 AND ballot_number_2019 IS NOT NULL AND ballot_number_2019 > 0) OR "
        "(NOT contested_2019 AND ballot_number_2019 IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_parties_nomor_urut_2024_sesuai_keikutsertaan"),
        "parties",
        "(contested_2024 AND ballot_number_2024 IS NOT NULL AND ballot_number_2024 > 0) OR "
        "(NOT contested_2024 AND ballot_number_2024 IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_parties_nomor_urut_2024_sesuai_keikutsertaan"), "parties", type_="check"
    )
    op.drop_constraint(
        op.f("ck_parties_nomor_urut_2019_sesuai_keikutsertaan"), "parties", type_="check"
    )
    op.drop_constraint("uq_parties_ballot_number_2024", "parties", type_="unique")
    op.drop_constraint("uq_parties_ballot_number_2019", "parties", type_="unique")
    op.drop_column("parties", "ballot_number_2024")
    op.drop_column("parties", "ballot_number_2019")
