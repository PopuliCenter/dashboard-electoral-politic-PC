"""Formula analitik elektoral (T4.2). Murni: tidak menyentuh database.

Formula (CLAUDE.md, SDD bagian 21):

- Vote share = suara / total suara sah x 100, dalam kontestasi dan wilayah yang sama.
- Swing = vote share periode baru - periode sebelumnya, dalam poin persentase.
- Margin = suara pemenang - suara peringkat kedua.
- Turnout = pengguna hak pilih / pemilih terdaftar x 100.
- Partai dominan = suara terbanyak pada kontestasi dan wilayah yang sama.

Prinsip yang berlaku untuk semua fungsi:

1. Angka yang tidak bisa dihitung dari data yang ada dikembalikan sebagai
   `Unavailable` beserta alasannya, tidak pernah ditaksir (aturan data 1).
2. Fungsi tidak tahu kontestasi; pemanggil yang menjamin semua masukan berasal
   dari satu kontestasi (aturan data 3). Swing memeriksa jenis kontestasinya.
3. Pembulatan urusan tampilan. Fungsi mengembalikan nilai penuh.
"""

from collections import defaultdict
from collections.abc import Collection, Hashable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from app.models.enums import DataStatus, ElectionType


class Unavailable(StrEnum):
    """Alasan sebuah angka tidak bisa ditampilkan. Nilainya teks antarmuka."""

    NO_DATA = "data tidak tersedia"
    INCOMPLETE = "data belum lengkap"
    NEW_PARTY = "baru"
    NOT_CONTESTED = "tidak ikut pemilu ini"
    UNMATCHED = "wilayah belum dipadankan"
    # Dipakai lapisan API saat fungsi di sini menolak data mustahil
    # (InconsistentDataError): angkanya tidak ditampilkan, halaman tetap jalan.
    INCONSISTENT = "data tidak konsisten"


class InconsistentDataError(ValueError):
    """Masukan yang mustahil secara aritmetika, misalnya suara melebihi suara sah.

    Data seperti ini seharusnya sudah tertahan rekonsiliasi; bila sampai di sini,
    lebih baik gagal keras daripada menampilkan persentase yang keliru.
    """


# --------------------------------------------------------------------------- #
# Status data turunan
# --------------------------------------------------------------------------- #

# Makin besar makin lemah. Angka turunan (persentase, swing, pemenang) tidak boleh
# tampil lebih resmi daripada bahan terlemahnya.
_STATUS_STRENGTH = {
    DataStatus.OFFICIAL: 0,
    DataStatus.UNOFFICIAL: 1,
    DataStatus.INTERNAL_AGGREGATE: 2,
}


def weakest_status(statuses: Iterable[DataStatus | None]) -> DataStatus | None:
    """Status terlemah di antara bahan sebuah angka turunan; None bila tak ada bahan."""
    present = [s for s in statuses if s is not None]
    return max(present, key=_STATUS_STRENGTH.__getitem__) if present else None


# --------------------------------------------------------------------------- #
# Vote share, swing, turnout
# --------------------------------------------------------------------------- #


def _check_count(name: str, value: int) -> None:
    if value < 0:
        raise InconsistentDataError(f"{name} negatif: {value}")


def vote_share(votes: int | None, valid_votes: int | None) -> float | Unavailable:
    """Persentase suara terhadap suara sah di kontestasi dan wilayah yang sama.

    Penyebutnya suara sah resmi, bukan jumlah suara partai yang kebetulan ada:
    bila suara sah tidak tersedia, vote share juga tidak tersedia.
    """
    if votes is None or valid_votes is None or valid_votes == 0:
        return Unavailable.NO_DATA
    _check_count("suara", votes)
    _check_count("suara sah", valid_votes)
    if votes > valid_votes:
        raise InconsistentDataError(f"suara ({votes}) melebihi suara sah ({valid_votes})")
    return votes / valid_votes * 100


def swing(new_share: float | Unavailable, old_share: float | Unavailable) -> float | Unavailable:
    """Selisih vote share dalam poin persentase (baru - lama)."""
    if isinstance(new_share, Unavailable):
        return new_share
    if isinstance(old_share, Unavailable):
        return old_share
    return new_share - old_share


def turnout(voters_turned_out: int | None, registered_voters: int | None) -> float | Unavailable:
    """Partisipasi. Boleh di atas 100: pemilih tambahan (DPTb) dan khusus (DPK)
    tidak tercatat di DPT, jadi itu bukan galat."""
    if voters_turned_out is None or registered_voters is None or registered_voters == 0:
        return Unavailable.NO_DATA
    _check_count("pengguna hak pilih", voters_turned_out)
    _check_count("pemilih terdaftar", registered_voters)
    return voters_turned_out / registered_voters * 100


# --------------------------------------------------------------------------- #
# Peringkat: partai dominan dan margin
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Ranking[K: Hashable]:
    # Lebih dari satu bila seri di puncak.
    leaders: tuple[K, ...]
    leader_votes: int
    # None bila hanya ada satu peserta.
    runner_up_votes: int | None

    @property
    def tie(self) -> bool:
        return len(self.leaders) > 1

    @property
    def margin(self) -> int | None:
        """Suara pemenang - suara peringkat kedua; 0 bila seri."""
        if self.tie:
            return 0
        if self.runner_up_votes is None:
            return None
        return self.leader_votes - self.runner_up_votes


def rank[K: Hashable](
    votes: Mapping[K, int | None], expected: Collection[K]
) -> Ranking[K] | Unavailable:
    """Peringkat peserta di satu wilayah dan satu kontestasi.

    `expected` adalah semua peserta kontestasi itu (partai peserta atau paslon).
    Bila ada peserta yang angkanya tidak tersedia, pemenang dan margin tidak
    bisa dipastikan: hasilnya `INCOMPLETE`, bukan pemenang di antara yang ada.
    Peserta di `votes` yang tidak ada di `expected` diabaikan.
    """
    if not expected:
        return Unavailable.NO_DATA
    present = {k: v for k, v in votes.items() if k in expected and v is not None}
    if not present:
        return Unavailable.NO_DATA
    if len(present) < len(expected):
        return Unavailable.INCOMPLETE
    for value in present.values():
        _check_count("suara", value)

    top = max(present.values())
    leaders = tuple(sorted((k for k, v in present.items() if v == top), key=repr))
    if len(leaders) > 1:
        # Seri: peringkat kedua adalah sesama pemuncak, bukan peringkat ketiga.
        runner_up: int | None = top
    else:
        rest = [v for k, v in present.items() if k not in leaders]
        runner_up = max(rest) if rest else None
    return Ranking(leaders, top, runner_up)


def dominant[K: Hashable](
    votes: Mapping[K, int | None], expected: Collection[K]
) -> tuple[K, ...] | Unavailable:
    """Peserta dengan suara terbanyak. Lebih dari satu berarti seri."""
    result = rank(votes, expected)
    return result if isinstance(result, Unavailable) else result.leaders


def margin[K: Hashable](
    votes: Mapping[K, int | None], expected: Collection[K]
) -> int | Unavailable:
    result = rank(votes, expected)
    if isinstance(result, Unavailable):
        return result
    if result.margin is None:
        return Unavailable.NO_DATA
    return result.margin


# --------------------------------------------------------------------------- #
# Swing antar pemilu lewat padanan wilayah
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AreaVotes:
    """Suara satu partai dan suara sah di satu wilayah, satu kontestasi."""

    party_votes: int | None
    valid_votes: int | None


@dataclass(frozen=True)
class MatchedUnit[R: Hashable]:
    """Satu unit padanan: wilayah lama dan baru yang saling terhubung.

    1:1 untuk wilayah tetap atau berganti kode; 1:n bila mekar; n:1 bila
    bergabung; n:m bila keduanya. Swing dihitung pada unit ini dengan
    menjumlahkan suara resmi di tiap sisi, bukan dengan membagi suara.
    """

    old_regions: frozenset[R]
    new_regions: frozenset[R]


def matched_units[R: Hashable](crosswalk: Iterable[tuple[R, R]]) -> list[MatchedUnit[R]]:
    """Kelompokkan pasangan (wilayah lama, wilayah baru) menjadi unit padanan.

    Unit adalah komponen terhubung pada graf padanan. Wilayah tanpa baris
    padanan tidak masuk unit mana pun, jadi swing-nya `UNMATCHED`.
    """
    # Union-find kecil; jumlah kecamatan Jawa Barat ratusan, bukan jutaan.
    parent: dict[tuple[str, R], tuple[str, R]] = {}

    def find(node: tuple[str, R]) -> tuple[str, R]:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for old, new in crosswalk:
        a, b = find(("old", old)), find(("new", new))
        if a != b:
            parent[a] = b

    groups: dict[tuple[str, R], tuple[set[R], set[R]]] = defaultdict(lambda: (set(), set()))
    for node in list(parent):
        side, region = node
        olds, news = groups[find(node)]
        (olds if side == "old" else news).add(region)
    return [MatchedUnit(frozenset(o), frozenset(n)) for o, n in groups.values()]


def aggregate[R: Hashable](
    regions: frozenset[R], data: Mapping[R, AreaVotes]
) -> AreaVotes | Unavailable:
    """Jumlahkan suara partai dan suara sah; semua wilayah unit wajib punya angka."""
    party_total = 0
    valid_total = 0
    for region in regions:
        area = data.get(region)
        if area is None or area.party_votes is None or area.valid_votes is None:
            # Satu wilayah tanpa angka membuat jumlah unit tidak bisa dipastikan.
            return Unavailable.INCOMPLETE if len(regions) > 1 else Unavailable.NO_DATA
        party_total += area.party_votes
        valid_total += area.valid_votes
    return AreaVotes(party_total, valid_total)


@dataclass(frozen=True)
class SwingInput[R: Hashable]:
    election_type_old: ElectionType
    election_type_new: ElectionType
    contested_old: bool
    contested_new: bool
    old: Mapping[R, AreaVotes]
    new: Mapping[R, AreaVotes]


def party_swing[R: Hashable](
    data: SwingInput[R], units: Iterable[MatchedUnit[R]]
) -> dict[MatchedUnit[R], float | Unavailable]:
    """Swing satu partai di setiap unit padanan.

    Partai yang hanya ikut pemilu baru diberi label `NEW_PARTY`, yang hanya ikut
    pemilu lama `NOT_CONTESTED` (aturan data 4).
    """
    if data.election_type_old is not data.election_type_new:
        raise ValueError(
            f"swing hanya dalam satu jenis kontestasi, bukan {data.election_type_old.value} "
            f"ke {data.election_type_new.value}"
        )
    results: dict[MatchedUnit[R], float | Unavailable] = {}
    for unit in units:
        if not data.contested_old and data.contested_new:
            results[unit] = Unavailable.NEW_PARTY
            continue
        if not data.contested_new:
            results[unit] = Unavailable.NOT_CONTESTED
            continue
        old = aggregate(unit.old_regions, data.old)
        new = aggregate(unit.new_regions, data.new)
        if isinstance(old, Unavailable):
            results[unit] = old
        elif isinstance(new, Unavailable):
            results[unit] = new
        else:
            results[unit] = swing(
                vote_share(new.party_votes, new.valid_votes),
                vote_share(old.party_votes, old.valid_votes),
            )
    return results


def unit_index[R: Hashable](
    units: Iterable[MatchedUnit[R]], *, side: str
) -> dict[R, MatchedUnit[R]]:
    """Wilayah -> unit padanannya, untuk satu sisi ("old" atau "new").

    Dibangun sekali lalu dipakai untuk banyak wilayah. Wilayah yang tidak ada di
    indeks belum dipadankan.
    """
    if side not in ("old", "new"):
        raise ValueError(f"side harus 'old' atau 'new', bukan {side!r}")
    return {
        region: unit
        for unit in units
        for region in (unit.old_regions if side == "old" else unit.new_regions)
    }


def unit_of[R: Hashable](
    region: R, index: Mapping[R, MatchedUnit[R]]
) -> MatchedUnit[R] | Unavailable:
    """Unit padanan sebuah wilayah dari `unit_index`, atau `UNMATCHED`."""
    return index.get(region, Unavailable.UNMATCHED)


def restrict_units[R: Hashable](
    units: Iterable[MatchedUnit[R]], valid_old: Collection[R], valid_new: Collection[R]
) -> tuple[list[MatchedUnit[R]], list[MatchedUnit[R]]]:
    """Pisahkan unit yang semua wilayahnya berlaku dari yang tidak.

    Padanan yang merujuk wilayah di luar himpunan yang berlaku (misalnya pecahan
    yang masa berlakunya keliru) tidak boleh dipotong lalu tampak seperti unit
    1:1 yang sah: seluruh unitnya dianggap belum dipadankan.
    """
    usable: list[MatchedUnit[R]] = []
    broken: list[MatchedUnit[R]] = []
    for unit in units:
        if unit.old_regions <= set(valid_old) and unit.new_regions <= set(valid_new):
            usable.append(unit)
        else:
            broken.append(unit)
    return usable, broken


@dataclass(frozen=True)
class ParentUnits[R: Hashable]:
    units: list[MatchedUnit[R]]
    # Wilayah induk yang belum bisa dipadankan dari unit turunannya.
    unmatched_old: frozenset[R]
    unmatched_new: frozenset[R]


def derive_parent_units[R: Hashable](
    child_units: Iterable[MatchedUnit[R]],
    old_children: Mapping[R, Collection[R]],
    new_children: Mapping[R, Collection[R]],
) -> ParentUnits[R]:
    """Unit padanan tingkat induk (kab/kota) dari unit tingkat anak (kecamatan).

    `old_children`/`new_children`: induk -> semua anaknya yang berlaku. Sebuah
    unit induk sah hanya bila:

    - setiap unit anak di dalamnya berada di bawah satu induk lama dan satu induk
      baru (unit yang melintasi dua induk membuat induk-induk itu belum
      dipadankan, bukan dipaksakan), dan
    - setiap anak dari induk-induk itu ikut di salah satu unit anak (satu
      kecamatan tanpa padanan membuat kab/kotanya belum dipadankan).

    Hanya STRUKTUR unit yang diturunkan; angkanya tetap dari baris tingkat induk.
    """
    old_parent = {child: parent for parent, kids in old_children.items() for child in kids}
    new_parent = {child: parent for parent, kids in new_children.items() for child in kids}
    tainted_old: set[R] = set()
    tainted_new: set[R] = set()
    edges: list[tuple[R, R]] = []
    covered_old: set[R] = set()
    covered_new: set[R] = set()

    for unit in child_units:
        olds = {old_parent.get(c) for c in unit.old_regions}
        news = {new_parent.get(c) for c in unit.new_regions}
        covered_old |= unit.old_regions
        covered_new |= unit.new_regions
        known_olds = {p for p in olds if p is not None}
        known_news = {p for p in news if p is not None}
        if len(olds) == 1 and len(news) == 1 and known_olds and known_news:
            edges.append((next(iter(known_olds)), next(iter(known_news))))
        else:
            tainted_old |= known_olds
            tainted_new |= known_news

    for parent, kids in old_children.items():
        if not set(kids) <= covered_old:
            tainted_old.add(parent)
    for parent, kids in new_children.items():
        if not set(kids) <= covered_new:
            tainted_new.add(parent)

    units: list[MatchedUnit[R]] = []
    unmatched_old = set(old_children) - {o for o, _ in edges}
    unmatched_new = set(new_children) - {n for _, n in edges}
    for unit in matched_units(edges):
        if unit.old_regions & tainted_old or unit.new_regions & tainted_new:
            unmatched_old |= unit.old_regions
            unmatched_new |= unit.new_regions
        else:
            units.append(unit)
    return ParentUnits(units, frozenset(unmatched_old), frozenset(unmatched_new))
