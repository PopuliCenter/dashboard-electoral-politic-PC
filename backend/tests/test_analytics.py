"""Formula analitik elektoral (T4.2). Semua angka fiktif dan dihitung tangan."""

import pytest

from app.models.enums import ElectionType
from app.services.analytics import (
    AreaVotes,
    InconsistentDataError,
    MatchedUnit,
    SwingInput,
    Unavailable,
    dominant,
    margin,
    matched_units,
    party_swing,
    rank,
    swing,
    turnout,
    unit_of,
    vote_share,
)

DPR = ElectionType.LEGISLATIVE_DPR

# --------------------------------------------------------------------------- #
# Vote share
# --------------------------------------------------------------------------- #


def test_vote_share_contoh_dasar() -> None:
    assert vote_share(250, 1000) == 25.0
    assert vote_share(0, 1000) == 0.0
    assert vote_share(1000, 1000) == 100.0
    assert vote_share(1, 3) == pytest.approx(33.3333333)


@pytest.mark.parametrize(
    ("suara", "sah"), [(None, 1000), (250, None), (None, None), (0, 0), (5, 0)]
)
def test_vote_share_tidak_tersedia_tidak_ditaksir(suara: int | None, sah: int | None) -> None:
    assert vote_share(suara, sah) is Unavailable.NO_DATA


def test_vote_share_suara_melebihi_suara_sah_gagal_keras() -> None:
    with pytest.raises(InconsistentDataError, match="melebihi suara sah"):
        vote_share(1001, 1000)


def test_vote_share_angka_negatif_gagal_keras() -> None:
    with pytest.raises(InconsistentDataError, match="negatif"):
        vote_share(-1, 1000)


# --------------------------------------------------------------------------- #
# Swing
# --------------------------------------------------------------------------- #


def test_swing_poin_persentase() -> None:
    # Contoh SDD 21.2: 20% -> 27% = +7 poin.
    assert swing(27.0, 20.0) == pytest.approx(7.0)
    assert swing(20.0, 27.0) == pytest.approx(-7.0)
    assert swing(15.0, 15.0) == 0.0


def test_swing_meneruskan_alasan_tidak_tersedia() -> None:
    assert swing(Unavailable.NO_DATA, 20.0) is Unavailable.NO_DATA
    assert swing(27.0, Unavailable.INCOMPLETE) is Unavailable.INCOMPLETE


# --------------------------------------------------------------------------- #
# Turnout
# --------------------------------------------------------------------------- #


def test_turnout() -> None:
    assert turnout(800, 1000) == 80.0
    assert turnout(0, 1000) == 0.0


def test_turnout_boleh_di_atas_seratus() -> None:
    """Pemilih DPTb dan DPK tidak tercatat di DPT."""
    assert turnout(1020, 1000) == pytest.approx(102.0)


@pytest.mark.parametrize(("hadir", "dpt"), [(None, 1000), (800, None), (800, 0)])
def test_turnout_tidak_tersedia(hadir: int | None, dpt: int | None) -> None:
    assert turnout(hadir, dpt) is Unavailable.NO_DATA


# --------------------------------------------------------------------------- #
# Partai dominan dan margin
# --------------------------------------------------------------------------- #

PESERTA = {"UJI_A", "UJI_B", "UJI_C"}


def test_partai_dominan_dan_margin() -> None:
    suara = {"UJI_A": 500, "UJI_B": 300, "UJI_C": 200}
    hasil = rank(suara, PESERTA)
    assert not isinstance(hasil, Unavailable)
    assert hasil.leaders == ("UJI_A",)
    assert (hasil.leader_votes, hasil.runner_up_votes, hasil.margin) == (500, 300, 200)
    assert dominant(suara, PESERTA) == ("UJI_A",)
    assert margin(suara, PESERTA) == 200


def test_seri_di_puncak_tidak_dipilih_acak() -> None:
    suara = {"UJI_A": 400, "UJI_B": 400, "UJI_C": 200}
    assert dominant(suara, PESERTA) == ("UJI_A", "UJI_B")
    assert margin(suara, PESERTA) == 0
    hasil = rank(suara, PESERTA)
    assert not isinstance(hasil, Unavailable) and hasil.tie


def test_seri_di_peringkat_kedua_tidak_mengubah_margin() -> None:
    assert margin({"UJI_A": 500, "UJI_B": 300, "UJI_C": 300}, PESERTA) == 200


def test_angka_nol_tetap_dihitung_sebagai_ada() -> None:
    assert dominant({"UJI_A": 0, "UJI_B": 0, "UJI_C": 1}, PESERTA) == ("UJI_C",)


def test_peserta_yang_angkanya_tidak_ada_membuat_hasil_belum_lengkap() -> None:
    """UJI_C tidak ada datanya: bisa saja ia pemenangnya."""
    suara = {"UJI_A": 500, "UJI_B": 300}
    assert dominant(suara, PESERTA) is Unavailable.INCOMPLETE
    assert margin(suara, PESERTA) is Unavailable.INCOMPLETE
    assert dominant({**suara, "UJI_C": None}, PESERTA) is Unavailable.INCOMPLETE


def test_tanpa_data_sama_sekali() -> None:
    assert dominant({}, PESERTA) is Unavailable.NO_DATA
    assert dominant({"UJI_A": 1}, set()) is Unavailable.NO_DATA


def test_peserta_di_luar_daftar_diabaikan() -> None:
    """Partai yang tidak ikut kontestasi ini tidak boleh menang di sini."""
    suara = {"UJI_A": 5, "UJI_B": 3, "UJI_C": 2, "UJI_Z": 999}
    assert dominant(suara, PESERTA) == ("UJI_A",)


def test_margin_satu_peserta_tidak_terdefinisi() -> None:
    assert margin({"1": 100}, {"1"}) is Unavailable.NO_DATA
    assert dominant({"1": 100}, {"1"}) == ("1",)


def test_paslon_pilpres_dengan_nomor_urut() -> None:
    assert dominant({1: 300, 2: 700}, {1, 2}) == (2,)
    assert margin({1: 300, 2: 700}, {1, 2}) == 400


# --------------------------------------------------------------------------- #
# Unit padanan
# --------------------------------------------------------------------------- #


def test_padanan_satu_satu_mekar_dan_gabung() -> None:
    units = matched_units(
        [
            ("K1", "K1"),  # tetap
            ("K2", "K2b"),  # berganti kode
            ("K3", "K3a"),  # mekar
            ("K3", "K3b"),
            ("K4", "K45"),  # bergabung
            ("K5", "K45"),
        ]
    )
    assert set(units) == {
        MatchedUnit(frozenset({"K1"}), frozenset({"K1"})),
        MatchedUnit(frozenset({"K2"}), frozenset({"K2b"})),
        MatchedUnit(frozenset({"K3"}), frozenset({"K3a", "K3b"})),
        MatchedUnit(frozenset({"K4", "K5"}), frozenset({"K45"})),
    }


def test_padanan_berantai_menjadi_satu_unit() -> None:
    """K6 mekar menjadi K6a dan K6b, lalu K6b bergabung dengan pecahan K7."""
    units = matched_units([("K6", "K6a"), ("K6", "K6b"), ("K7", "K6b"), ("K7", "K7a")])
    assert units == [MatchedUnit(frozenset({"K6", "K7"}), frozenset({"K6a", "K6b", "K7a"}))]


def test_kode_yang_sama_di_kedua_sisi_tidak_tertukar() -> None:
    """Kode 'K1' lama dan 'K1' baru adalah simpul berbeda pada graf."""
    units = matched_units([("K1", "K2"), ("K2", "K1")])
    assert len(units) == 2


def test_wilayah_tanpa_padanan() -> None:
    units = matched_units([("K1", "K1")])
    assert unit_of("K9", units, side="new") is Unavailable.UNMATCHED
    assert unit_of("K1", units, side="old") == units[0]


# --------------------------------------------------------------------------- #
# Swing partai per unit padanan
# --------------------------------------------------------------------------- #


def _swing_input(**kwargs: object) -> SwingInput[str]:
    base: dict[str, object] = {
        "election_type_old": DPR,
        "election_type_new": DPR,
        "contested_old": True,
        "contested_new": True,
        "old": {},
        "new": {},
    }
    base.update(kwargs)
    return SwingInput(**base)  # type: ignore[arg-type]


def test_swing_unit_satu_satu() -> None:
    unit = MatchedUnit(frozenset({"K1"}), frozenset({"K1"}))
    hasil = party_swing(
        _swing_input(old={"K1": AreaVotes(200, 1000)}, new={"K1": AreaVotes(270, 1000)}),
        [unit],
    )
    assert hasil[unit] == pytest.approx(7.0)


def test_swing_wilayah_mekar_dijumlahkan_di_sisi_baru() -> None:
    # 2019: K3 20% (200/1000). 2024: K3a 150/600 + K3b 90/600 = 240/1200 = 20%.
    unit = MatchedUnit(frozenset({"K3"}), frozenset({"K3a", "K3b"}))
    hasil = party_swing(
        _swing_input(
            old={"K3": AreaVotes(200, 1000)},
            new={"K3a": AreaVotes(150, 600), "K3b": AreaVotes(90, 600)},
        ),
        [unit],
    )
    assert hasil[unit] == pytest.approx(0.0)


def test_swing_wilayah_bergabung_dijumlahkan_di_sisi_lama() -> None:
    # 2019: (100 + 300) / (500 + 1500) = 20%. 2024: 500 / 2000 = 25%.
    unit = MatchedUnit(frozenset({"K4", "K5"}), frozenset({"K45"}))
    hasil = party_swing(
        _swing_input(
            old={"K4": AreaVotes(100, 500), "K5": AreaVotes(300, 1500)},
            new={"K45": AreaVotes(500, 2000)},
        ),
        [unit],
    )
    assert hasil[unit] == pytest.approx(5.0)


def test_swing_unit_dengan_satu_wilayah_tanpa_data_tidak_ditaksir() -> None:
    unit = MatchedUnit(frozenset({"K3"}), frozenset({"K3a", "K3b"}))
    hasil = party_swing(
        _swing_input(old={"K3": AreaVotes(200, 1000)}, new={"K3a": AreaVotes(150, 600)}),
        [unit],
    )
    assert hasil[unit] is Unavailable.INCOMPLETE


def test_swing_tanpa_suara_sah_tidak_tersedia() -> None:
    unit = MatchedUnit(frozenset({"K1"}), frozenset({"K1"}))
    hasil = party_swing(
        _swing_input(old={"K1": AreaVotes(200, None)}, new={"K1": AreaVotes(270, 1000)}),
        [unit],
    )
    assert hasil[unit] is Unavailable.NO_DATA


def test_partai_baru_diberi_label_bukan_swing() -> None:
    unit = MatchedUnit(frozenset({"K1"}), frozenset({"K1"}))
    hasil = party_swing(_swing_input(contested_old=False, new={"K1": AreaVotes(50, 1000)}), [unit])
    assert hasil[unit] is Unavailable.NEW_PARTY


def test_partai_yang_tidak_ikut_pemilu_baru() -> None:
    unit = MatchedUnit(frozenset({"K1"}), frozenset({"K1"}))
    hasil = party_swing(_swing_input(contested_new=False), [unit])
    assert hasil[unit] is Unavailable.NOT_CONTESTED


def test_swing_lintas_jenis_kontestasi_ditolak() -> None:
    with pytest.raises(ValueError, match="satu jenis kontestasi"):
        party_swing(_swing_input(election_type_new=ElectionType.PRESIDENTIAL), [])
