"""Kontrak skema tabel inti (T2.1). Tidak butuh database."""

from app.models import Base
from app.models.enums import (
    CrosswalkRelation,
    DataStatus,
    ElectionType,
    JobStatus,
    RegionLevel,
    RoleCode,
    ValidationStatus,
)

TABEL_INTI = {
    "regions",
    "region_crosswalk",
    "elections",
    "parties",
    "candidate_pairs",
    "election_results",
    "candidate_results",
    "region_turnout",
    "data_sources",
    "dataset_versions",
    "ingestion_jobs",
    "audit_logs",
    "users",
    "roles",
    "user_sessions",  # T5.1
}

TABEL_HASIL = ("election_results", "candidate_results", "region_turnout")


def test_semua_tabel_inti_ada() -> None:
    assert set(Base.metadata.tables) == TABEL_INTI


def test_tabel_fase_dua_belum_dibuat() -> None:
    """demographics, public_budgets, media_aggregates dan survey_aggregates ditunda."""
    ditunda = {
        "demographics",
        "public_budgets",
        "public_policies",
        "media_aggregates",
        "survey_aggregates",
        "candidates",
    }
    assert ditunda.isdisjoint(set(Base.metadata.tables))


def test_vote_share_tidak_disimpan() -> None:
    """Vote share dihitung dari suara, bukan sumber kebenaran di tabel."""
    for nama in TABEL_HASIL:
        kolom = set(Base.metadata.tables[nama].columns.keys())
        assert "vote_share" not in kolom, nama
        assert "swing" not in kolom, nama


def test_setiap_baris_hasil_membawa_sumber_dan_status() -> None:
    """Aturan data 5: sumber, versi dataset, dan status data wajib dan NOT NULL."""
    for nama in TABEL_HASIL:
        tabel = Base.metadata.tables[nama]
        for wajib in ("source_id", "dataset_version_id", "data_status"):
            assert wajib in tabel.columns, f"{nama} kehilangan {wajib}"
            assert not tabel.columns[wajib].nullable, f"{nama}.{wajib} boleh NULL"


def test_hasil_partai_unik_per_kontestasi_wilayah_partai() -> None:
    """Aturan data 3: kontestasi tidak boleh tercampur, satu baris per kombinasi."""
    tabel = Base.metadata.tables["election_results"]
    kombinasi = {
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in tabel.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("election_id", "party_id", "region_id") in kombinasi


def test_geometri_wilayah_memakai_srid_4326() -> None:
    kolom = Base.metadata.tables["regions"].columns["geometry"]
    assert kolom.type.srid == 4326
    assert kolom.type.geometry_type == "MULTIPOLYGON"


def test_wilayah_punya_masa_berlaku() -> None:
    """Kecamatan yang mekar atau berganti kode butuh valid_from dan valid_until."""
    kolom = Base.metadata.tables["regions"].columns
    assert not kolom["valid_from"].nullable
    assert kolom["valid_until"].nullable


def test_nilai_enum_sesuai_kontrak() -> None:
    assert [e.value for e in RegionLevel] == ["province", "regency", "district"]
    assert [e.value for e in ElectionType] == [
        "presidential",
        "legislative_dpr",
        "legislative_dprd_province",
    ]
    assert [e.value for e in DataStatus] == ["official", "unofficial", "internal_aggregate"]
    assert [e.value for e in CrosswalkRelation] == ["same", "split", "merged", "recoded"]
    assert [e.value for e in ValidationStatus] == ["pending", "passed", "failed"]
    assert [e.value for e in JobStatus] == ["queued", "running", "succeeded", "failed"]
    assert [e.value for e in RoleCode] == ["admin", "researcher"]


def test_dprd_kabupaten_kota_dan_pilkada_bukan_jenis_yang_sah() -> None:
    """Fase 1 hanya tiga kontestasi (REVISI-v1.1 bagian 2)."""
    nilai = {e.value for e in ElectionType}
    assert "legislative_dprd_regency" not in nilai
    assert "regional_head" not in nilai


def test_warna_partai_tidak_disimpan_di_database() -> None:
    """Warna partai datang dari konfigurasi, bukan kolom tabel (T4.5)."""
    kolom = set(Base.metadata.tables["parties"].columns.keys())
    assert "color" not in kolom
    assert "party_color" not in kolom


def test_partai_menandai_keikutsertaan_tiap_pemilu() -> None:
    """Swing hanya untuk partai yang ikut di kedua pemilu (aturan data 4)."""
    kolom = Base.metadata.tables["parties"].columns
    assert not kolom["contested_2019"].nullable
    assert not kolom["contested_2024"].nullable


def test_pengguna_hanya_menyimpan_hash_password() -> None:
    kolom = set(Base.metadata.tables["users"].columns.keys())
    assert "password_hash" in kolom
    assert "password" not in kolom
