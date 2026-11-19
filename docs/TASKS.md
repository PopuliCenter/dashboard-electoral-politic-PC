# Backlog Eksekusi — Fase 1 (MVP v1.1)

Kerjakan berurutan. Satu tugas = satu commit atau PR kecil. Centang setelah kriteria selesai terpenuhi. Jangan lompat melewati gerbang.

## Tahap 0 — Fondasi repo (bisa langsung dikerjakan)

- [x] T0.1 Inisialisasi Git, `.gitignore` (termasuk `.env`, `data/raw/`, `data/tiles/`), `README.md` singkat.
- [x] T0.2 Struktur folder sesuai `CLAUDE.md`.
- [x] T0.3 `docker-compose.yml` untuk pengembangan lokal: `db` (postgis/postgis), `api` (FastAPI), `web` (Next.js). `.env.example` tanpa rahasia.
- [x] T0.4 Backend kosong: FastAPI + SQLAlchemy 2 + Alembic + pytest; endpoint `GET /api/v1/health` yang mengecek koneksi database.
- [x] T0.5 Frontend kosong: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui; satu halaman yang memanggil `/health`.
- [x] T0.6 Lint dan format: ruff + mypy (backend), eslint + prettier (frontend). Satu perintah `make check`.

Selesai bila: `docker compose up` menyalakan ketiganya dan `make check` hijau. **Terpenuhi 19 November 2026:** `/api/v1/health` melaporkan PostgreSQL 16.4 dan PostGIS 3.4.3 terhubung, halaman web membacanya, `ruff`, `mypy`, `pytest` (4 lolos), `eslint`, `tsc`, dan `prettier` semuanya hijau.

## Tahap 1 — Inventaris data (minggu 1–2, sebagian besar pekerjaan manusia)

- [ ] T1.1 `docs/data-inventory.md`: per kontestasi (Pilpres, DPR RI, DPRD Provinsi) × tahun (2019, 2024) × tingkat (kab/kota, kecamatan): dokumen ada atau tidak, format, URL, tanggal unduh.
- [ ] T1.2 Arsipkan dokumen mentah ke `data/raw/<sumber>/<tahun>/` dan salin ke NAS. Catat checksum SHA-256 di `data/raw/MANIFEST.csv`.
- [ ] T1.3 Kode wilayah Kemendagri Jawa Barat (provinsi, kab/kota, kecamatan) sebagai CSV di `data/reference/`.
- [ ] T1.4 Batas wilayah (kab/kota, kecamatan) sebagai GeoJSON atau GeoPackage di `data/reference/`, dengan sumber dan tahun versi.

**Gerbang 1:** hitung persentase kecamatan yang punya rekapitulasi resmi. Di bawah ambang yang disepakati → MVP berhenti di kabupaten/kota; catat keputusannya di `docs/decisions.md`.

## Tahap 2 — Skema dan wilayah (minggu 3–5)

- [ ] T2.1 Migrasi Alembic untuk tabel inti (lihat skema di `CLAUDE.md`).
- [ ] T2.2 Skrip impor wilayah + geometri; uji: 27 kab/kota, setiap kecamatan punya induk dan geometri valid (`ST_IsValid`).
- [ ] T2.3 Tabel `region_crosswalk` 2019→2024 dan skrip pengisiannya; uji: setiap kecamatan 2019 terpetakan atau ditandai eksplisit.
- [ ] T2.4 Bangun vector tiles (tippecanoe → PMTiles) untuk kab/kota dan kecamatan; simpan di `data/tiles/`.
- [ ] T2.5 Seed `parties` dan `elections` (6 kontestasi: 3 jenis × 2 tahun); tandai partai yang hanya ikut salah satu pemilu.

## Tahap 3 — Data elektoral (minggu 6–9)

- [ ] T3.1 Format impor baku (CSV) + validator: kode wilayah dikenal, suara tidak negatif, tidak duplikat, kontestasi dan partai cocok.
- [ ] T3.2 Ekstraktor PDF/Excel per jenis dokumen → format impor baku. Hasil ekstraksi selalu masuk staging dulu.
- [ ] T3.3 Skrip rekonsiliasi: total per kab/kota dibanding rekapitulasi resmi; keluaran laporan selisih.
- [ ] T3.4 Promosi staging → produksi hanya untuk dataset yang lolos; tulis `dataset_versions` dan `audit_logs`.
- [ ] T3.5 Laporan kelengkapan per kontestasi dan tingkat wilayah.

**Gerbang 2:** selisih total per kabupaten/kota harus 0 untuk keenam kontestasi.

## Tahap 4 — API dan antarmuka (minggu 10–13)

- [ ] T4.1 Endpoint: `/regions`, `/regions/{id}/children`, `/elections`, `/elections/{id}/results`, `/elections/compare`, `/parties`, `/parties/{id}/results`. Setiap respons membawa `source` dan `data_status`.
- [ ] T4.2 Fungsi analitik teruji: vote share, swing (hanya unit terpadankan dan partai di kedua pemilu), margin, turnout, partai dominan.
- [ ] T4.3 Halaman peta: MapLibre + PMTiles, filter (tahun, jenis, kab/kota), 4 lapisan, drill-down ke kecamatan, panel detail, legenda.
- [ ] T4.4 Halaman partai: peringkat, sebaran per kab/kota, perubahan suara (ECharts).
- [ ] T4.5 Warna partai dari konfigurasi, bukan hard-code.

## Tahap 5 — Manajemen data dan akses (minggu 14–15)

- [ ] T5.1 Login, sesi aman, hashing password, dua peran (Admin, Peneliti).
- [ ] T5.2 Antarmuka impor: unggah CSV/XLSX → hasil validasi → setujui → promosi.
- [ ] T5.3 Halaman metadata sumber dan riwayat versi dataset.
- [ ] T5.4 Ekspor CSV/XLSX dari peta dan halaman partai, menyertakan sumber dan status data.

## Tahap 6 — Operasi (minggu 16–17)

- [ ] T6.1 `docker-compose.prod.yml` untuk Server A dan Server B; Nginx + TLS; Server B tanpa port publik.
- [ ] T6.2 Skrip `pg_dump` terenkripsi (malam + setelah impor), retensi 7 hari; dokumentasi tarikan dari NAS lewat WireGuard.
- [ ] T6.3 Skrip uji restore ke staging + pembanding jumlah baris dan total suara.
- [ ] T6.4 Rate limiting, validasi input, header keamanan, audit log.
- [ ] T6.5 Uji beban: 5 pengguna bersamaan; target 3 detik (kab/kota) dan 5 detik (kecamatan).

**Gerbang 3:** uji restore berhasil dan tercatat.

## Tahap 7 — UAT dan rilis (minggu 18–20)

- [ ] T7.1 Skenario UAT dari `SDD.md` bagian 19, disesuaikan dengan cakupan v1.1.
- [ ] T7.2 Perbaikan temuan UAT.
- [ ] T7.3 Panduan admin, panduan pengguna, prosedur backup dan pemulihan.
