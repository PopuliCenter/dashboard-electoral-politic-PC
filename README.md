# Populi Political & Electoral Intelligence Dashboard

Dashboard internal Populi Center untuk memetakan dan membandingkan hasil pemilu.
Pilot fase 1: **Provinsi Jawa Barat, Pemilu 2019 dan 2024**, sampai tingkat kecamatan,
untuk tiga kontestasi: Pilpres, DPR RI, dan DPRD Provinsi.

Acuan kerja: `docs/REVISI-v1.1.md` (cakupan aktif) dan `docs/TASKS.md` (urutan eksekusi).

## Menjalankan secara lokal

```bash
cp .env.example .env     # sesuaikan bila perlu
docker compose up        # db (PostGIS), api (FastAPI), web (Next.js)
```

| Layanan | Alamat | Keterangan |
| --- | --- | --- |
| web | http://localhost:3000 | Next.js App Router |
| api | http://localhost:8000/api/v1/health | FastAPI, cek koneksi database |
| api (dokumentasi) | http://localhost:8000/docs | OpenAPI |
| db | localhost:5432 | PostgreSQL 16 + PostGIS 3.4 |

## Perintah

```bash
make check      # lint + type check + test (backend dan frontend)
make migrate    # alembic upgrade head di dalam kontainer api
make up         # docker compose up -d
make down       # docker compose down
make fmt        # format ulang kode
```

`make` tidak tersedia di Windows secara bawaan. Dari PowerShell pakai shim:

```powershell
.\make.ps1 check
```

Tanpa keduanya, isi tiap target ada di `Makefile` dan bisa dijalankan langsung.

## Struktur repo

```
backend/    FastAPI, SQLAlchemy 2, Alembic, pytest
frontend/   Next.js App Router, TypeScript, Tailwind, shadcn/ui
pipeline/   extract (PDF/Excel KPU), validate, load (staging -> produksi), tiles (PMTiles)
data/       raw (tidak masuk Git), reference (kode dan batas wilayah), tiles (hasil, tidak masuk Git)
deploy/     compose produksi, nginx, skrip backup dan uji restore
docs/       PRD, SDD, revisi v1.1, backlog, keputusan
```

## Aturan data

Sembilan aturan wajib ada di `CLAUDE.md` bagian "Aturan data". Tiga yang paling sering kena:

1. Angka suara tidak pernah dikarang atau diperkirakan. Data yang tidak ada ditandai tidak tersedia.
2. Pilpres, DPR RI, dan DPRD Provinsi tidak pernah dicampur dalam kueri, agregasi, maupun tampilan.
3. Setiap baris hasil membawa sumber, versi dataset, dan status data (`official`, `unofficial`, `internal_aggregate`).

## Status

Tahap 0 (fondasi repo) selesai. Tahap 1 (inventaris dokumen KPU, kode dan batas wilayah)
menunggu dokumen dari manusia; `data/raw/` dan `data/reference/` masih kosong.
