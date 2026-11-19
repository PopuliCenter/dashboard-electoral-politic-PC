# Populi Political & Electoral Intelligence Dashboard

Dashboard web internal Populi Center untuk memetakan dan membandingkan hasil pemilu. Pilot: Provinsi Jawa Barat, Pemilu 2019 dan 2024.

## Dokumen acuan

| File | Isi | Kedudukan |
| --- | --- | --- |
| `docs/REVISI-v1.1.md` | Cakupan, arsitektur, KPI, dan jadwal yang direvisi | **Berlaku.** Menang bila bertentangan dengan v1.0 |
| `docs/TASKS.md` | Backlog eksekusi per tahap, dengan gerbang | Urutan kerja |
| `docs/PRD.md` | PRD asli v1.0 | Acuan kebutuhan dan user story |
| `docs/SDD.md` | SDD asli v1.0: skema, API, formula, tata kelola data | Acuan desain; abaikan bagian yang dicabut v1.1 |

Baca `docs/REVISI-v1.1.md` dan `docs/TASKS.md` sebelum mulai mengerjakan apa pun.

## Cakupan aktif (fase 1)

Masuk:

- Peta Jawa Barat: provinsi → 27 kabupaten/kota → kecamatan.
- Pilpres, DPR RI, DPRD Provinsi; tahun 2019 dan 2024.
- Lapisan peta: partai dominan, vote share, swing, partisipasi.
- Halaman partai; impor CSV/XLSX dengan validasi; ekspor; login dengan peran Admin dan Peneliti.

**Jangan dibangun di fase 1** (tolak atau tanyakan dulu bila diminta): tingkat desa/kelurahan, DPRD kabupaten/kota, Pilkada, demografi, kebijakan publik dan APBD, profil kandidat dan kepala daerah, media, survei, asisten AI, scraper KPU, prediksi.

## Stack

- Frontend: Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, MapLibre GL JS, Apache ECharts.
- Backend: Python, FastAPI, SQLAlchemy 2, Alembic, Pydantic, pytest.
- Data: PostgreSQL + PostGIS, Pandas, Camelot (ekstraksi PDF), tippecanoe → PMTiles.
- Operasi: Docker Compose, Nginx, cron, `pg_dump`.

**Tidak dipakai:** Redis, Deck.gl, Prefect, Scrapy, Playwright. Jangan menambahkannya, atau dependensi berat lain, tanpa persetujuan.

## Struktur repo

```
backend/
  app/            # api/, models/, schemas/, services/ (analitik), core/ (config, auth)
  alembic/
  tests/
frontend/
  src/app/        # halaman: peta, partai, data, login
  src/components/
  src/lib/        # klien API, util peta
pipeline/
  extract/        # PDF/Excel KPU -> format impor baku
  validate/       # validator dan rekonsiliasi
  load/           # staging -> produksi
  tiles/          # pembuatan PMTiles
data/
  raw/            # dokumen mentah (tidak masuk Git; ada MANIFEST.csv)
  reference/      # kode wilayah, batas wilayah, daftar partai
  tiles/          # hasil PMTiles (tidak masuk Git)
deploy/           # compose produksi, nginx, skrip backup dan uji restore
docs/
```

## Arsitektur

- **Server A (aplikasi, publik, port 443 saja):** Nginx, Next.js, FastAPI, PostgreSQL + PostGIS produksi, tiles statis.
- **Server B (data, hanya lewat VPN):** ekstraksi, database staging, dump backup, lingkungan UAT.
- **NAS kantor:** menarik dump dan arsip mentah dari Server B lewat WireGuard. Server tidak menyimpan kredensial NAS.
- Data baru: Server B → validasi di staging → promosi ke produksi. Tidak ada jalur tulis langsung ke produksi.

Lokal: semuanya jalan lewat `docker compose up`.

## Skema database (inti)

Dasarnya `docs/SDD.md` bagian 11, dengan perubahan v1.1 berikut:

- `regions`: `region_code` (kode Kemendagri), `region_level` (`province` | `regency` | `district`), `parent_id`, `geometry`, `valid_from`, `valid_until`.
- `region_crosswalk`: `from_region_id`, `to_region_id`, `from_year`, `to_year`, `relation` (`same` | `split` | `merged` | `recoded`).
- `elections`: `election_type` (`presidential` | `legislative_dpr` | `legislative_dprd_province`), `election_year`, `election_date`.
- `parties`: tambah `contested_2019`, `contested_2024` (atau tabel `party_elections`).
- `election_results`: per `election_id` × `region_id` × `party_id`; `vote_count`, `source_id`, `dataset_version_id`, `data_status`.
- `candidate_results`: hanya untuk Pilpres (pasangan calon).
- `region_turnout`: per `election_id` × `region_id`; `registered_voters`, `voters_turned_out`, `valid_votes`, `invalid_votes`.
- `data_sources`, `dataset_versions`, `ingestion_jobs`, `audit_logs`, `users`, `roles`.
- `data_status`: `official` | `unofficial` | `internal_aggregate`.

Ditunda (fase 2+): `demographics`, `public_budgets`, `public_policies`, `media_aggregates`, `survey_aggregates`, profil kandidat.

UUID sebagai kunci internal; kode wilayah resmi sebagai kunci referensi eksternal. `vote_share` dihitung, tidak disimpan sebagai sumber kebenaran.

## Aturan data (wajib)

1. Jangan pernah mengarang, memperkirakan, atau mengisi angka suara. Data yang tidak ada ditandai tidak tersedia.
2. Data uji dan contoh harus jelas fiktif ("Partai A", kode wilayah uji) dan tidak boleh masuk database produksi.
3. Jangan mencampur kontestasi: Pilpres, DPR RI, dan DPRD Provinsi selalu dipisah di kueri, agregasi, dan tampilan.
4. Swing hanya untuk partai yang ikut di kedua pemilu dan unit wilayah yang sudah dipadankan lewat `region_crosswalk`. Partai baru diberi label "baru".
5. Setiap baris hasil punya sumber, versi dataset, dan `data_status`. Status ikut tampil di UI dan file ekspor.
6. Data gagal validasi tidak boleh menggantikan data produksi. Promosi hanya lewat `pipeline/load`.
7. Rekonsiliasi: total per kabupaten/kota harus sama persis dengan rekapitulasi resmi (selisih 0).
8. Dokumen mentah di `data/raw/` tidak diubah; perubahan dicatat sebagai versi baru.
9. Tidak ada data individu (responden, pemilih) di repo atau database ini.

## Formula

- Vote share = suara partai ÷ total suara sah × 100, dalam kontestasi dan wilayah yang sama.
- Swing = vote share periode baru − periode sebelumnya, dalam poin persentase.
- Margin = suara pemenang − suara peringkat kedua.
- Turnout = pengguna hak pilih ÷ pemilih terdaftar × 100.
- Partai dominan = suara terbanyak pada kontestasi dan wilayah yang sama.

Semua formula ada di `backend/app/services/` dan punya unit test.

## Konvensi

- API di bawah `/api/v1`; respons hasil pemilu selalu menyertakan `source` dan `data_status`.
- Kode, nama tabel, dan nama kolom dalam bahasa Inggris; teks antarmuka dan dokumentasi dalam bahasa Indonesia.
- Perubahan skema hanya lewat migrasi Alembic.
- Warna partai dari konfigurasi, bukan hard-code.
- Rahasia hanya di `.env` (tidak masuk Git); sediakan `.env.example`.
- Tulis test untuk formula, validator, dan endpoint sebelum menandai tugas selesai.
- Commit kecil, pesan jelas, satu tugas dari `docs/TASKS.md` per commit atau PR.

## Perintah

Diisi saat Tahap 0 selesai (target):

```
docker compose up          # jalankan db, api, web secara lokal
make check                 # lint + type check + test
make migrate               # alembic upgrade head
```

## Cara bekerja

- Ambil tugas pertama yang belum dicentang di `docs/TASKS.md`; kerjakan sampai kriteria selesainya terpenuhi; centang.
- Berhenti dan tanyakan di setiap **Gerbang**; keputusan gerbang dicatat di `docs/decisions.md`.
- Tahap 1 butuh dokumen dari manusia. Bila `data/raw/` atau `data/reference/` kosong, kerjakan Tahap 0 dan bagian Tahap 2–3 yang bisa diuji dengan data fiktif, lalu laporkan apa yang masih ditunggu.

## Keputusan terbuka

Belum diputuskan; jangan diasumsikan di kode (lihat `docs/REVISI-v1.1.md` bagian 10):

- Dua server KVM 2, atau satu server ditambah NAS.
- Apakah data Sirekap/Situng boleh ditampilkan dengan label tidak resmi.
- Ambang kelengkapan kecamatan untuk Gerbang 1.
- Lokasi dan pengelola NAS.
