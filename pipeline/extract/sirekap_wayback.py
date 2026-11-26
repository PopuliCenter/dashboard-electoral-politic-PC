"""Pembanding TIDAK RESMI: salinan Sirekap 2024 dari Internet Archive (sekali jalan).

Sirekap (sirekap-obj-data.kpu.go.id) sudah offline. Yang tersisa hanya snapshot
Internet Archive yang diambil SAAT PENGHITUNGAN MASIH BERJALAN (Februari-April
2024). Angkanya:

- bukan hasil resmi (REVISI-v1.1 bagian 3: Sirekap hanya pembanding, berstatus
  tidak resmi), dan
- tidak lengkap: setiap baris membawa progres TPS saat snapshot diambil.

Karena itu keluaran skrip ini hanya untuk dibandingkan dengan rekapitulasi
resmi, bukan untuk dimuat sebagai hasil. Sirekap tidak memuat DPT, suara sah,
atau suara tidak sah, jadi persentase suara tidak bisa dihitung darinya.

Ini bukan scraper terjadwal: skrip membaca arsip publik sekali, pelan (jeda
beberapa detik per permintaan), dan tidak menyentuh server KPU.

Pemakaian (dari akar repo, Python 3.11+, hanya pustaka standar):

    python pipeline/extract/sirekap_wayback.py plan       # cari snapshot terakhir
    python pipeline/extract/sirekap_wayback.py fetch      # unduh ke data/raw/
    python pipeline/extract/sirekap_wayback.py extract    # CSV ke data/staging/
    python pipeline/extract/sirekap_wayback.py manifest   # catat di MANIFEST.csv
"""

import argparse
import csv
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import manifest

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "sirekap-wayback" / "2024"
STAGING = ROOT / "data" / "staging" / "sirekap-wayback-2024"
HOST = "sirekap-obj-data.kpu.go.id"
USER_AGENT = "Mozilla/5.0 (compatible; populi-data-inventory/1.0)"
PAUSE = 3
CONTESTS = {
    "ppwp": "presidential",
    "pdpr": "legislative_dpr",
    "pdprdp": "legislative_dprd_province",
}
MASTERS = ["pemilu/ppwp.json", "pemilu/partai.json"]
SOURCE = "Internet Archive - salinan Sirekap KPU 2024 (TIDAK RESMI)"


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url: str, tries: int = 5) -> tuple[str, bytes]:
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=180) as response:
                body, final = response.read(), response.geturl()
            time.sleep(PAUSE)
            return final, body
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            wait = 15 * (attempt + 1)
            print(f"  ulang dalam {wait} detik ({exc})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"gagal setelah {tries} percobaan: {url}")


def cdx_latest(prefix: str, regex: str) -> dict[str, str]:
    """Snapshot 200 terakhir per URL di bawah prefix yang cocok regex."""
    query = urllib.parse.urlencode(
        {
            "url": prefix,
            "matchType": "prefix",
            "output": "json",
            "fl": "original,timestamp",
            "filter": ["statuscode:200", "original:" + regex],
        },
        doseq=True,
    )
    _, body = http_get("http://web.archive.org/cdx/search/cdx?" + query)
    rows = json.loads(body or b"[]")[1:]
    latest: dict[str, str] = {}
    for original, stamp in rows:
        path = re.sub(r"^https?://[^/]+/", "", original).split("?")[0]
        latest[path] = max(latest.get(path, ""), stamp)
    return latest


def plan() -> None:
    wanted: dict[str, str] = {}
    for contest in CONTESTS:
        found = cdx_latest(
            f"{HOST}/pemilu/hhcw/{contest}/32", rf".*/hhcw/{contest}/32(/32[0-9]{{2}})?\.json"
        )
        wanted |= found
        kab = sum(1 for p in found if re.search(r"/32/32\d\d\.json$", p))
        province = "ada" if f"pemilu/hhcw/{contest}/32.json" in found else "TIDAK ADA"
        print(f"{contest}: provinsi {province}, kab/kota {kab}/27")
    for master in MASTERS:
        found = cdx_latest(f"{HOST}/{master}", r".*\.json")
        if master in found:
            wanted[master] = found[master]
        print(f"{master}: {'ada' if master in found else 'TIDAK ADA'}")
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "plan.json").write_text(json.dumps(wanted, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{len(wanted)} berkas direncanakan -> {(RAW / 'plan.json').relative_to(ROOT)}")


def fetch() -> None:
    wanted = json.loads((RAW / "plan.json").read_text(encoding="utf-8"))
    log_path = RAW / "log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    for path, stamp in sorted(wanted.items()):
        target = RAW / path
        if target.exists():
            continue
        final, body = http_get(f"http://web.archive.org/web/{stamp}id_/https://{HOST}/{path}")
        if body[:2] == b"\x1f\x8b":  # isi asli dikirim ber-gzip; ini pengodean transport
            body = gzip.decompress(body)
        json.loads(body)  # harus JSON utuh
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        snapshot = re.search(r"/web/(\d{14})", final)
        log[path] = {
            "archive_url": final,
            "snapshot": snapshot.group(1) if snapshot else stamp,
            "retrieved_at": now(),
        }
        log_path.write_text(json.dumps(log, indent=1, sort_keys=True), encoding="utf-8")
        print(f"{target.relative_to(ROOT)} ({len(body)} byte, snapshot {log[path]['snapshot']})")


def dotted(code: str) -> str:
    """Kode KPU 2024 tanpa titik ('320101') -> kode Kemendagri bertitik ('32.01.01')."""
    return ".".join([code[:2], code[2:4], code[4:6]][: len(code) // 2]).rstrip(".")


def load_reference() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    ref = ROOT / "data" / "reference"
    with (ref / "kode_wilayah_jabar.csv").open(encoding="utf-8") as handle:
        regions = {row["region_code"]: row["name"] for row in csv.DictReader(handle)}
    with (ref / "parties.csv").open(encoding="utf-8") as handle:
        parties = {
            row["ballot_number_2024"]: row["party_code"]
            for row in csv.DictReader(handle)
            if row["ballot_number_2024"]
        }
    pairs: dict[str, str] = {}
    master = RAW / "pemilu" / "ppwp.json"
    if master.exists():
        for key, item in json.loads(master.read_text(encoding="utf-8")).items():
            number = item.get("nomor_urut") if isinstance(item, dict) else None
            if number is not None:
                pairs[key] = str(number)
    return regions, parties, pairs


def extract() -> None:
    regions, parties, pairs = load_reference()
    log = json.loads((RAW / "log.json").read_text(encoding="utf-8"))
    STAGING.mkdir(parents=True, exist_ok=True)
    columns = [
        "election_type",
        "region_level",
        "region_code",
        "region_code_kpu",
        "region_name",
        "participant_key",
        "kpu_key",
        "vote_count",
        "tps_progress_pct",
        "file_tps_counted",
        "file_tps_total",
        "sirekap_ts",
        "archive_snapshot",
        "archive_url",
        "data_status",
        "notes",
    ]
    unknown_regions: set[str] = set()
    for contest, election_type in CONTESTS.items():
        for level in ("regency", "district"):
            pattern = (
                f"pemilu/hhcw/{contest}/32.json"
                if level == "regency"
                else f"pemilu/hhcw/{contest}/32/32*.json"
            )
            rows = []
            for path in sorted(RAW.glob(pattern)):
                rel = path.relative_to(RAW).as_posix()
                data = json.loads(path.read_text(encoding="utf-8"))
                progress = data.get("progres") or {}
                for code, values in sorted((data.get("table") or {}).items()):
                    region = dotted(code)
                    name = regions.get(region, "")
                    if not name:
                        unknown_regions.add(region)
                    for key, votes in values.items():
                        if key in {"psu", "persen", "status_progress"}:
                            continue
                        participant = (
                            pairs.get(key, "") if contest == "ppwp" else parties.get(key, "")
                        )
                        rows.append(
                            {
                                "election_type": election_type,
                                "region_level": level,
                                "region_code": region,
                                "region_code_kpu": code,
                                "region_name": name,
                                "participant_key": participant,
                                "kpu_key": key,
                                "vote_count": "" if votes is None else votes,
                                "tps_progress_pct": values.get("persen", ""),
                                "file_tps_counted": progress.get("progres", ""),
                                "file_tps_total": progress.get("total", ""),
                                "sirekap_ts": data.get("ts", ""),
                                "archive_snapshot": log[rel]["snapshot"],
                                "archive_url": log[rel]["archive_url"],
                                "data_status": "unofficial",
                                "notes": "snapshot penghitungan berjalan, bukan hasil akhir"
                                + (
                                    ""
                                    if name
                                    else "; kode wilayah tidak ada di kode_wilayah_jabar.csv"
                                )
                                + ("" if participant else "; peserta belum terpetakan"),
                            }
                        )
            target = STAGING / f"{contest}_{'kabkota' if level == 'regency' else 'kecamatan'}.csv"
            with target.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            regions_seen = len({r["region_code"] for r in rows})
            print(f"{target.relative_to(ROOT)}: {len(rows)} baris, {regions_seen} wilayah")
    if unknown_regions:
        print(
            f"kode KPU yang tidak ada di referensi BIG ({len(unknown_regions)}): "
            f"{', '.join(sorted(unknown_regions)[:20])}"
        )


def record() -> None:
    log = json.loads((RAW / "log.json").read_text(encoding="utf-8"))
    entries = []
    for rel, meta in sorted(log.items()):
        path = RAW / rel
        contest = rel.split("/")[2] if rel.startswith("pemilu/hhcw/") else ""
        level = "" if not contest else ("regency" if rel.endswith("/32.json") else "district")
        note = "TIDAK RESMI; snapshot Internet Archive " + meta["snapshot"]
        if contest:
            data = json.loads(path.read_text(encoding="utf-8"))
            progress = data.get("progres") or {}
            counted, total = progress.get("progres", "?"), progress.get("total", "?")
            note += f"; data Sirekap {data.get('ts', '?')}; progres {counted}/{total} TPS"
        entries.append(
            manifest.Entry(
                path=path,
                source=SOURCE,
                retrieved_at=meta["retrieved_at"],
                source_url=meta["archive_url"],
                election_year="2024" if contest else "",
                election_type=CONTESTS.get(contest, ""),
                region_level=level,
                notes=note,
            )
        )
    added, skipped = manifest.record(entries)
    print(f"MANIFEST: {added} ditambah, {skipped} sudah tercatat")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["plan", "fetch", "extract", "manifest"])
    args = parser.parse_args()
    {"plan": plan, "fetch": fetch, "extract": extract, "manifest": record}[args.command]()


if __name__ == "__main__":
    main()
