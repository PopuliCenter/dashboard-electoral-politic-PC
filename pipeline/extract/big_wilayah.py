"""Kode dan batas wilayah Jawa Barat dari Badan Informasi Geospasial (T1.3, T1.4).

Sumber: layanan ArcGIS REST BIG "Batas Wilayah Administrasi" (layer kab/kota dan
kecamatan). Setiap poligon membawa kode Kemendagri (KDPPUM, KDPKAB, KDCPUM);
kolom kode BPS di layanan ini kosong.

Pemakaian (dari akar repo, Python 3.11+, hanya pustaka standar):

    python pipeline/extract/big_wilayah.py fetch --edition 2026-06
    python pipeline/extract/big_wilayah.py build --edition 2026-06
    python pipeline/extract/big_wilayah.py manifest --edition 2026-06

- fetch: unduh resolusi penuh dan versi tergeneralisasi (toleransi 0,0001 derajat,
  sekitar 11 m, dilakukan server BIG) ke data/raw/big/<edisi>/. Berkas yang sudah
  ada tidak diunduh ulang.
- build: susun data/reference/kode_wilayah_jabar.csv dari atribut resolusi penuh,
  dan data/reference/batas_wilayah_{kabkota,kecamatan}_jabar.geojson dari versi
  tergeneralisasi. Poligon tanpa kode (BIG: "Area Tidak Terdefinisi") tidak ikut.
- manifest: catat semua berkas mentah edisi itu ke data/raw/MANIFEST.csv.

Edisi BIG menggambarkan batas saat diunduh, bukan batas pada hari pemungutan
suara 2019 atau 2024. Padanan antartahun dikerjakan di T2.3.
"""

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import manifest

ROOT = Path(__file__).resolve().parents[2]
SERVICE = "https://geoservices.big.go.id/rbi/rest/services/BATASWILAYAH"
LAYERS = {"kabkota": ("BATAS_KABKOTA_AR", 9), "kecamatan": ("BATAS_KECAMATAN_AR", 100)}
WHERE = "WADMPR='Jawa Barat'"
GENERALIZE = "0.0001"
USER_AGENT = "Mozilla/5.0 (compatible; populi-data-inventory/1.0)"
SOURCE = "BIG - Batas Wilayah Administrasi"


def raw_dir(edition: str) -> Path:
    return ROOT / "data" / "raw" / "big" / edition


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def query_url(service: str, offset: int, count: int, generalized: bool) -> str:
    params = {
        "where": WHERE,
        "outFields": "*",
        "returnGeometry": "true",
        "orderByFields": "OBJECTID",
        "resultOffset": offset,
        "resultRecordCount": count,
        "outSR": "4326",
        "f": "geojson",
    }
    if generalized:
        params |= {"maxAllowableOffset": GENERALIZE, "geometryPrecision": "5"}
    return f"{SERVICE}/{service}/MapServer/0/query?" + urllib.parse.urlencode(params)


def count(service: str) -> int:
    url = f"{SERVICE}/{service}/MapServer/0/query?" + urllib.parse.urlencode(
        {"where": WHERE, "returnCountOnly": "true", "f": "json"}
    )
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ) as r:
        return int(json.load(r)["count"])


def fetch(edition: str) -> None:
    out = raw_dir(edition)
    log_path = out / "retrieved_at.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    for generalized, folder in ((False, out), (True, out / "generalized")):
        folder.mkdir(parents=True, exist_ok=True)
        for level, (service, step) in LAYERS.items():
            total = count(service)
            for index, offset in enumerate(range(0, total, step)):
                target = folder / f"{level}_jabar_part{index:02d}.geojson"
                if target.exists():
                    continue
                url = query_url(service, offset, step, generalized)
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(request, timeout=300) as response:
                    target.write_bytes(response.read())
                log[target.relative_to(out).as_posix()] = {"retrieved_at": now(), "url": url}
                print(f"{target.relative_to(ROOT)} {target.stat().st_size} byte")
                time.sleep(2)
    log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")


def features(folder: Path, level: str) -> list[dict]:
    found: list[dict] = []
    for path in sorted(folder.glob(f"{level}_jabar_part*.geojson")):
        found += json.loads(path.read_text(encoding="utf-8"))["features"]
    if not found:
        sys.exit(f"tidak ada berkas {level} di {folder}; jalankan fetch dulu")
    return found


def text(props: dict, key: str) -> str:
    return (props.get(key) or "").strip()


def regency_name(props: dict) -> str:
    """BIG menulis kabupaten tanpa awalan ('Bogor') dan kota dengan awalan ('Kota Bogor')."""
    name = text(props, "WADMKK")
    return name if props.get("TIPADM") == 5 else f"Kabupaten {name}"


def build(edition: str) -> None:
    out = raw_dir(edition)
    full = {level: features(out, level) for level in LAYERS}
    general = {level: features(out / "generalized", level) for level in LAYERS}
    stamp = f"{SOURCE}, edisi {edition}"

    kab = sorted((f["properties"] for f in full["kabkota"]), key=lambda p: text(p, "KDPKAB"))
    kec_all = [f["properties"] for f in full["kecamatan"]]
    kec = sorted((p for p in kec_all if text(p, "KDCPUM")), key=lambda p: text(p, "KDCPUM"))
    skipped = len(kec_all) - len(kec)
    kab_codes = {text(p, "KDPKAB") for p in kab}
    orphans = [text(p, "KDCPUM") for p in kec if text(p, "KDCPUM")[:5] not in kab_codes]
    if len(kab) != 27 or len(kab_codes) != 27 or orphans:
        sys.exit(f"data tidak wajar: {len(kab)} kab/kota, induk tidak dikenal {orphans[:5]}")
    if len({text(p, "KDCPUM") for p in kec}) != len(kec):
        sys.exit("kode kecamatan ganda di data BIG")

    reference = ROOT / "data" / "reference"
    columns = [
        "region_code",
        "region_level",
        "parent_code",
        "name",
        "source_name",
        "regency_type",
        "source",
        "boundary_metadata",
        "verified_by",
        "notes",
    ]
    rows = [
        {
            "region_code": "32",
            "region_level": "province",
            "parent_code": "",
            "name": "Jawa Barat",
            "source_name": text(kab[0], "WADMPR"),
            "regency_type": "",
            "source": stamp,
            "boundary_metadata": "",
            "verified_by": "",
            "notes": "",
        }
    ]
    for p in kab:
        rows.append(
            {
                "region_code": text(p, "KDPKAB"),
                "region_level": "regency",
                "parent_code": "32",
                "name": regency_name(p),
                "source_name": text(p, "WADMKK"),
                "regency_type": "kota" if p.get("TIPADM") == 5 else "kabupaten",
                "source": stamp,
                "boundary_metadata": text(p, "METADATA"),
                "verified_by": "",
                "notes": "",
            }
        )
    for p in kec:
        code = text(p, "KDCPUM")
        rows.append(
            {
                "region_code": code,
                "region_level": "district",
                "parent_code": code[:5],
                "name": text(p, "WADMKC"),
                "source_name": text(p, "WADMKC"),
                "regency_type": "",
                "source": stamp,
                "boundary_metadata": text(p, "METADATA"),
                "verified_by": "",
                "notes": "",
            }
        )
    with (reference / "kode_wilayah_jabar.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    names = {r["region_code"]: r["name"] for r in rows}
    for level, key, parent_of in (
        ("kabkota", "KDPKAB", lambda code: "32"),
        ("kecamatan", "KDCPUM", lambda code: code[:5]),
    ):
        items = []
        for f in general[level]:
            code = text(f["properties"], key)
            if not code:
                continue
            items.append(
                {
                    "type": "Feature",
                    "geometry": f["geometry"],
                    "properties": {
                        "region_code": code,
                        "region_level": "regency" if level == "kabkota" else "district",
                        "parent_code": parent_of(code),
                        "name": names[code],
                        "boundary_metadata": text(f["properties"], "METADATA"),
                    },
                }
            )
        items.sort(key=lambda f: f["properties"]["region_code"])
        expected = len(kab) if level == "kabkota" else len(kec)
        if len(items) != expected:
            sys.exit(f"{level}: {len(items)} poligon tergeneralisasi, {expected} di resolusi penuh")
        collection = {
            "type": "FeatureCollection",
            "name": f"batas_wilayah_{level}_jabar",
            "source": stamp,
            "generalized_tolerance_degrees": float(GENERALIZE),
            "features": items,
        }
        path = reference / f"batas_wilayah_{level}_jabar.geojson"
        path.write_text(
            json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        print(f"{path.relative_to(ROOT)}: {len(items)} poligon, {path.stat().st_size} byte")
    print(
        "data/reference/kode_wilayah_jabar.csv: 1 provinsi, "
        f"{len(kab)} kab/kota, {len(kec)} kecamatan ({skipped} poligon tanpa kode dilewati)"
    )


def record(edition: str) -> None:
    out = raw_dir(edition)
    log_path = out / "retrieved_at.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    entries = []
    for path in sorted(out.rglob("*.geojson")):
        meta = log.get(path.relative_to(out).as_posix())
        if meta is None:
            sys.exit(f"{path}: tidak ada catatan waktu dan URL di {log_path.name}")
        level = "regency" if path.name.startswith("kabkota") else "district"
        kind = (
            "tergeneralisasi 0,0001 derajat"
            if path.parent.name == "generalized"
            else "resolusi penuh"
        )
        entries.append(
            manifest.Entry(
                path=path,
                source=f"{SOURCE} (edisi {edition})",
                retrieved_at=meta["retrieved_at"],
                source_url=meta["url"],
                region_level=level,
                notes=f"Jawa Barat, {kind}",
            )
        )
    added, skipped = manifest.record(entries)
    print(f"MANIFEST: {added} ditambah, {skipped} sudah tercatat")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["fetch", "build", "manifest"])
    parser.add_argument("--edition", required=True, help="edisi BIG, misal 2026-06")
    args = parser.parse_args()
    {"fetch": fetch, "build": build, "manifest": record}[args.command](args.edition)


if __name__ == "__main__":
    main()
