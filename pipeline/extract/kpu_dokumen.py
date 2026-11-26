"""Unduh dokumen hasil resmi yang tercatat di data/metadata/source_inventory.csv (T1.2).

Hanya baris dengan auto_fetch=ya, file_url, dan raw_path yang diunduh. Inventaris
adalah satu-satunya daftar: apa yang diunduh selalu sama dengan apa yang
tercatat. Sekali jalan, pelan, dan berkas yang sudah ada tidak diunduh ulang.

Setiap unduhan diperiksa tanda tangan berkasnya: halaman HTML (misalnya halaman
galat yang dikirim dengan status 200) ditolak, tidak disimpan sebagai dokumen.

Pemakaian (dari akar repo, Python 3.11+, hanya pustaka standar):

    python pipeline/extract/kpu_dokumen.py fetch
    python pipeline/extract/kpu_dokumen.py manifest
"""

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import manifest

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "data" / "metadata" / "source_inventory.csv"
LOG = ROOT / "data" / "raw" / "kpu-dokumen.log.json"
USER_AGENT = "Mozilla/5.0 (compatible; populi-data-inventory/1.0)"
PAUSE = 3
SIGNATURES = {".pdf": (b"%PDF",), ".xlsx": (b"PK\x03\x04",), ".csv": ()}
LEVELS = {"provinsi": "province", "kabupaten/kota": "regency", "kecamatan": "district"}


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows() -> list[dict[str, str]]:
    with INVENTORY.open(newline="", encoding="utf-8") as handle:
        return [
            r
            for r in csv.DictReader(handle)
            if r["auto_fetch"] == "ya" and r["file_url"] and r["raw_path"]
        ]


def check(body: bytes, suffix: str, url: str) -> None:
    head = body[:512].lstrip().lower()
    if head.startswith((b"<!doctype html", b"<html")):
        raise ValueError(f"isinya halaman HTML, bukan dokumen: {url}")
    signatures = SIGNATURES.get(suffix)
    if signatures is None:
        raise ValueError(f"jenis berkas {suffix} belum dikenal: {url}")
    if signatures and not body.startswith(signatures):
        raise ValueError(f"tanda tangan berkas tidak cocok dengan {suffix}: {url}")
    if suffix == ".csv":
        body.decode("utf-8-sig")  # CSV harus teks UTF-8


def fetch() -> None:
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    failed = []
    for row in rows():
        target = ROOT / row["raw_path"]
        if target.exists():
            continue
        url = row["file_url"]
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read()
            check(body, target.suffix.lower(), url)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            failed.append(f"{row['dataset_id']}: {exc}")
            print(f"GAGAL {row['dataset_id']}: {exc}", file=sys.stderr)
            time.sleep(PAUSE)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        log[row["raw_path"]] = {"dataset_id": row["dataset_id"], "url": url, "retrieved_at": now()}
        LOG.write_text(json.dumps(log, indent=1, sort_keys=True), encoding="utf-8")
        print(f"{row['raw_path']} ({len(body)} byte)")
        time.sleep(PAUSE)
    if failed:
        sys.exit(f"{len(failed)} gagal; perbarui availability_status di inventaris")


def record() -> None:
    log = json.loads(LOG.read_text(encoding="utf-8"))
    entries = []
    for row in rows():
        meta = log.get(row["raw_path"])
        if meta is None:
            continue
        entries.append(
            manifest.Entry(
                path=ROOT / row["raw_path"],
                source=f"{row['institution']}: {row['dataset_name']}",
                retrieved_at=meta["retrieved_at"],
                source_url=meta["url"],
                election_year=row["election_year"],
                election_type=row["election_type"],
                region_level=LEVELS.get(row["geographic_level"], ""),
                notes=f"{row['dataset_id']}; {row['data_status']}; {row['notes']}".rstrip("; "),
            )
        )
    added, skipped = manifest.record(entries)
    print(f"MANIFEST: {added} ditambah, {skipped} sudah tercatat")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["fetch", "manifest"])
    {"fetch": fetch, "manifest": record}[parser.parse_args().command]()


if __name__ == "__main__":
    main()
