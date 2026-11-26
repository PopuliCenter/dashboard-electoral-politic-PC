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

- [x] T1.1 `docs/data-inventory.md`: per kontestasi (Pilpres, DPR RI, DPRD Provinsi) × tahun (2019, 2024) × tingkat (kab/kota, kecamatan): dokumen ada atau tidak, format, URL, tanggal unduh. **26 November 2026:** rincian 61 sumber di `data/metadata/source_inventory.csv`. Rekap resmi kab/kota yang tersedia daring hanya DPR RI 2019; tingkat kecamatan 1–2 dari 27 kab/kota. Sisanya perlu permohonan PPID.
- [ ] T1.2 Arsipkan dokumen mentah ke `data/raw/<sumber>/<tahun>/` dan salin ke NAS. Catat checksum SHA-256 di `data/raw/MANIFEST.csv`. **26 November 2026, sebagian:** 153 berkas tercatat di MANIFEST (BIG, 26 dokumen KPU RI termasuk Lampiran I, II, dan III Kpt 360, 1 tabel BPS Pilpres per provinsi, 58 salinan Sirekap, 12 dokumen KPU Kab. Indramayu dan ekstraksinya, 6 DB1/D.HASIL Kota Bogor, 3 DB1 Sumedang, 3 peta GIS Kab. Bogor (pembanding), 2 publikasi BPS Jabar, 25 tabel BPS fase 2: DPD, jumlah pemilih, IDI, Indeks HAM, suara DPR per partai nasional). Ke-27 situs PPID KPU kab/kota sudah ditelusuri lewat Chrome. Di laptop pengelola, folder `data mentah` adalah pintasan ke `data/raw/` (lihat `docs/data-inventory.md`). Berkas dari luar skrip diarsipkan dengan `pipeline/extract/arsip_lokal.py`. Belum disalin ke NAS; dokumen Google Drive dan hasil PPID menyusul.
- [x] T1.3 Kode wilayah Kemendagri Jawa Barat (provinsi, kab/kota, kecamatan) sebagai CSV di `data/reference/`. **26 November 2026:** `kode_wilayah_jabar.csv` (1 + 27 + 627) dari BIG edisi Juni 2026; ke-627 kode kecamatan Sirekap 2024 cocok. **Menunggu verifikasi peneliti**; masa berlaku 2019 belum dicek.
- [x] T1.4 Batas wilayah (kab/kota, kecamatan) sebagai GeoJSON atau GeoPackage di `data/reference/`, dengan sumber dan tahun versi. **26 November 2026:** dari BIG edisi Juni 2026; resolusi penuh di `data/raw/big/` lolos `ST_IsValid`, versi tergeneralisasi di `data/reference/`. **Menunggu verifikasi peneliti** dan kepastian lisensi untuk repo publik.

**Gerbang 1:** hitung persentase kecamatan yang punya rekapitulasi resmi. Di bawah ambang yang disepakati → MVP berhenti di kabupaten/kota; catat keputusannya di `docs/decisions.md`.

## Tahap 2 — Skema dan wilayah (minggu 3–5)

- [x] T2.1 Migrasi Alembic untuk tabel inti (lihat skema di `CLAUDE.md`). **20 November 2026:** 14 tabel, `upgrade head` dan `downgrade base` pulang-pergi bersih, `alembic check` tanpa drift, 25 test lolos.
- [ ] T2.2 Skrip impor wilayah + geometri; uji: 27 kab/kota, setiap kecamatan punya induk dan geometri valid (`ST_IsValid`).
- [ ] T2.3 Tabel `region_crosswalk` 2019→2024 dan skrip pengisiannya; uji: setiap kecamatan 2019 terpetakan atau ditandai eksplisit.
- [ ] T2.4 Bangun vector tiles (tippecanoe → PMTiles) untuk kab/kota dan kecamatan; simpan di `data/tiles/`.
- [x] T2.5 Seed `parties` dan `elections` (6 kontestasi: 3 jenis × 2 tahun); tandai partai yang hanya ikut salah satu pemilu. **20 November 2026:** 20 partai, 6 kontestasi, 5 paslon; seed idempoten dan tercatat di `audit_logs`, 78 test lolos. **Data menunggu verifikasi peneliti** (`verified_by` kosong; produksi menolak).
- [ ] T2.6 Dapil dan peserta per dapil (DPR RI, DPRD Provinsi; 2019 dan 2024): daftar dapil, pemetaan kab/kota/kecamatan ke dapil, dan partai yang punya calon per dapil, semuanya lewat migrasi Alembic dan data referensi. **Butuh dokumen KPU:** penetapan dapil dan Daftar Calon Tetap per dapil (lihat T1.1). Sesudahnya: T3.5 dan T4.2 memakai peserta per dapil, dan validator T3.1 menolak suara partai di dapil yang tidak diikutinya. Keputusan: `docs/decisions.md`, "Review T3.4 — peserta per dapil".

## Tahap 3 — Data elektoral (minggu 6–9)

- [x] T3.1 Format impor baku (CSV) + validator: kode wilayah dikenal, suara tidak negatif, tidak duplikat, kontestasi dan partai cocok. **20 November 2026:** tiga jenis berkas (suara partai, suara paslon, partisipasi), format di `docs/format-impor.md`, `make validate f=...`; diuji dengan data fiktif, 129 test lolos. Belum dicoba pada data nyata: menunggu wilayah (T2.2).
- [ ] T3.2 Ekstraktor PDF/Excel per jenis dokumen → format impor baku. Hasil ekstraksi selalu masuk staging dulu.
- [ ] T3.3 Skrip rekonsiliasi: total per kab/kota dibanding rekapitulasi resmi; keluaran laporan selisih.
- [x] T3.4 Promosi staging → produksi hanya untuk dataset yang lolos; tulis `dataset_versions` dan `audit_logs`. **20 November 2026:** `make load`, `make datasets`, `make promote` (`backend/app/datasets/`); staging = database terpisah; diuji dengan data fiktif di dua database, 146 test lolos. Syarat rekonsiliasi T3.3 belum terpasang di gerbang promosi.
- [x] T3.5 Laporan kelengkapan per kontestasi dan tingkat wilayah. **20 November 2026:** `make completeness` (`backend/app/reports/`), teks atau CSV per wilayah, untuk produksi atau staging; diuji dengan data fiktif, 155 test lolos. Belum ada angka nyata: menunggu wilayah (T2.2) dan hasil (T3.2).

**Gerbang 2:** selisih total per kabupaten/kota harus 0 untuk keenam kontestasi.

## Tahap 4 — API dan antarmuka (minggu 10–13)

- [x] T4.1 Endpoint: `/regions`, `/regions/{id}/children`, `/elections`, `/elections/{id}/results`, `/elections/compare`, `/parties`, `/parties/{id}/results`. Setiap respons membawa `source` dan `data_status`. **20 November 2026:** ditambah `/regions/{id}`, `/elections/{id}`, `/parties/{id}`; angka tak terhitung dikirim `null` dengan alasan; 14 test API dengan data fiktif, 245 test lolos. **Belum ada login: jangan dibuka ke jaringan publik sebelum T5.1.** Peserta legislatif masih nasional sampai T2.6.
- [x] T4.2 Fungsi analitik teruji: vote share, swing (hanya unit terpadankan dan partai di kedua pemilu), margin, turnout, partai dominan. **20 November 2026:** `backend/app/services/analytics.py`, fungsi murni; 36 test dengan angka fiktif hitungan tangan, 191 test lolos. Belum dipakai endpoint (T4.1).
- [ ] T4.3 Halaman peta: MapLibre + PMTiles, filter (tahun, jenis, kab/kota), 4 lapisan, drill-down ke kecamatan, panel detail, legenda.
- [ ] T4.4 Halaman partai: peringkat, sebaran per kab/kota, perubahan suara (ECharts).
- [x] T4.5 Warna partai dari konfigurasi, bukan hard-code. **20 November 2026:** `data/reference/party_colors.csv` + validasi, warna dan `color_source` di `/parties`, palet cadangan bertanda. **Warna resmi belum diisi**: menunggu peneliti mencatat warna dari identitas visual resmi tiap partai beserta sumbernya.

## Tahap 5 — Manajemen data dan akses (minggu 14–15)

- [x] T5.1 Login, sesi aman, hashing password, dua peran (Admin, Peneliti). **20 November 2026:** scrypt (pustaka standar), sesi server-side dengan cookie HttpOnly/SameSite=Lax/Secure, penguncian akun, audit login, pemeriksaan Origin; semua endpoint data wajib login; CLI `make users`; halaman `/login`. 269 test lolos. Belum ada antarmuka pengelolaan pengguna di web (sementara lewat CLI).
- [ ] T5.2 Antarmuka impor: unggah CSV/XLSX → hasil validasi → setujui → promosi.
- [x] T5.3 Halaman metadata sumber dan riwayat versi dataset. **20 November 2026:** API `/sources`, `/sources/{id}`, `/datasets`, `/datasets/{nama}` (wajib login) dengan metadata SDD 12.4, versi yang berlaku, "digantikan oleh", dan kejadian dari `audit_logs`; halaman `/data`. 305 test lolos. Halaman riwayat per dataset di web belum ada (datanya sudah tersedia di API).
- [x] T5.4 Ekspor CSV/XLSX dari peta dan halaman partai, menyertakan sumber dan status data. **20 November 2026:** `/elections/{id}/results/export`, `/elections/compare/export`, `/parties/{id}/results/export` (`format=csv|xlsx`, wajib login, tercatat di `audit_logs`); openpyxl 3.1.5. 313 test lolos. Tombol unduh menyusul bersama halaman peta (T4.3) dan partai (T4.4); helper `exportUrl` sudah ada.

## Tahap 6 — Operasi (minggu 16–17)

- [ ] T6.1 `docker-compose.prod.yml` untuk Server A dan Server B; Nginx + TLS; Server B tanpa port publik. **Wajib:** Nginx meneruskan alamat IP asli (`X-Forwarded-For`/`X-Real-IP`) dan uvicorn dijalankan dengan `--proxy-headers --forwarded-allow-ips` yang hanya memercayai Nginx. Tanpa itu semua permintaan tampak dari IP Nginx dan penguncian login per akun+IP (T5.1) berperilaku seperti per akun saja.
- [ ] T6.2 Skrip `pg_dump` terenkripsi (malam + setelah impor), retensi 7 hari; dokumentasi tarikan dari NAS lewat WireGuard.
- [ ] T6.3 Skrip uji restore ke staging + pembanding jumlah baris dan total suara.
- [ ] T6.4 Rate limiting, validasi input, header keamanan, audit log.
- [ ] T6.5 Uji beban: 5 pengguna bersamaan; target 3 detik (kab/kota) dan 5 detik (kecamatan).

**Gerbang 3:** uji restore berhasil dan tercatat.

## Tahap 7 — UAT dan rilis (minggu 18–20)

- [ ] T7.1 Skenario UAT dari `SDD.md` bagian 19, disesuaikan dengan cakupan v1.1.
- [ ] T7.2 Perbaikan temuan UAT.
- [ ] T7.3 Panduan admin, panduan pengguna, prosedur backup dan pemulihan.
