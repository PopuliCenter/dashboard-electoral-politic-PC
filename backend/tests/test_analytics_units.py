"""Status turunan dan unit padanan tingkat induk (review T4.1), tanpa database."""

from app.models.enums import DataStatus
from app.services.analytics import (
    AreaVotes,
    MatchedUnit,
    Unavailable,
    aggregate,
    derive_parent_units,
    restrict_units,
    weakest_status,
)

OFF, UNOFF, AGG = DataStatus.OFFICIAL, DataStatus.UNOFFICIAL, DataStatus.INTERNAL_AGGREGATE


def u(old: set[str], new: set[str]) -> MatchedUnit[str]:
    return MatchedUnit(frozenset(old), frozenset(new))


def test_status_terlemah() -> None:
    assert weakest_status([OFF, OFF]) is OFF
    assert weakest_status([OFF, UNOFF]) is UNOFF
    assert weakest_status([UNOFF, AGG, OFF]) is AGG
    assert weakest_status([None, OFF]) is OFF
    assert weakest_status([]) is None


def test_agregasi_unit() -> None:
    data = {"A": AreaVotes(10, 100), "B": AreaVotes(20, 100), "C": AreaVotes(None, 100)}
    assert aggregate(frozenset({"A", "B"}), data) == AreaVotes(30, 200)
    assert aggregate(frozenset({"A", "C"}), data) is Unavailable.INCOMPLETE
    assert aggregate(frozenset({"C"}), data) is Unavailable.NO_DATA


def test_unit_yang_menyentuh_wilayah_tak_berlaku_dipisahkan() -> None:
    sah, rusak = u({"K1"}, {"K1"}), u({"K2"}, {"K2a", "K2x"})
    usable, broken = restrict_units([sah, rusak], {"K1", "K2"}, {"K1", "K2a"})
    assert (usable, broken) == ([sah], [rusak])


def test_unit_kabkota_dari_kecamatan_yang_terpadankan_penuh() -> None:
    hasil = derive_parent_units(
        [u({"A1"}, {"A1"}), u({"A2"}, {"A2a", "A2b"})],
        old_children={"A": ["A1", "A2"]},
        new_children={"A": ["A1", "A2a", "A2b"]},
    )
    assert hasil.units == [u({"A"}, {"A"})]
    assert not hasil.unmatched_old and not hasil.unmatched_new


def test_satu_kecamatan_tanpa_padanan_membuat_kabkota_belum_dipadankan() -> None:
    hasil = derive_parent_units(
        [u({"A1"}, {"A1"})],
        old_children={"A": ["A1", "A2"]},
        new_children={"A": ["A1"]},
    )
    assert hasil.units == []
    assert hasil.unmatched_old == {"A"} and hasil.unmatched_new == {"A"}


def test_unit_lintas_kabkota_tidak_dipaksakan() -> None:
    """Kecamatan B1 (kab/kota B) dan C2 (kab/kota C) bergabung menjadi C2 baru:
    satu unit kecamatan beranggota dua induk lama."""
    hasil = derive_parent_units(
        [u({"A1"}, {"A1"}), u({"B1", "C2"}, {"C2"}), u({"B2"}, {"B2"})],
        old_children={"A": ["A1"], "B": ["B1", "B2"], "C": ["C2"]},
        new_children={"A": ["A1"], "B": ["B2"], "C": ["C2"]},
    )
    assert hasil.units == [u({"A"}, {"A"})]
    assert hasil.unmatched_old == {"B", "C"}
    assert hasil.unmatched_new == {"B", "C"}


def test_kecamatan_pindah_kabkota_membentuk_unit_gabungan() -> None:
    """Kecamatan B1 pindah utuh dari B ke C. Setiap unit kecamatan tetap di bawah
    satu induk per sisi, jadi B dan C hanya bisa dibandingkan bersama (n:m),
    seperti kecamatan yang mekar atau bergabung."""
    hasil = derive_parent_units(
        [u({"B1"}, {"B1"}), u({"B2"}, {"B2"}), u({"C1"}, {"C1"})],
        old_children={"B": ["B1", "B2"], "C": ["C1"]},
        new_children={"B": ["B2"], "C": ["B1", "C1"]},
    )
    assert hasil.units == [u({"B", "C"}, {"B", "C"})]


def test_kabkota_mekar_menjadi_satu_unit_induk() -> None:
    """Kab/kota D mekar menjadi D dan E; semua kecamatannya terpadankan."""
    hasil = derive_parent_units(
        [u({"D1"}, {"D1"}), u({"D2"}, {"E1"})],
        old_children={"D": ["D1", "D2"]},
        new_children={"D": ["D1"], "E": ["E1"]},
    )
    assert hasil.units == [u({"D"}, {"D", "E"})]
