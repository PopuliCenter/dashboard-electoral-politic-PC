# Review: Data Requirements & Data Acquisition Plan v1.0

Per 26 November 2026. Dokumen yang direview: *Data Requirements & Data
Acquisition Plan, Populi Political Intelligence Dashboard, versi 1.0 (draft)*.

**Kesimpulan:** dokumen itu kerangka yang baik untuk seluruh umur proyek, tetapi
sebagai rencana fase 1 ia bertentangan dengan `REVISI-v1.1.md` di delapan hal.
Pengguna memutuskan (26 November 2026) untuk **mengikuti v1.1**: semua domain
dokumen tetap dicatat di inventaris dengan tanda fase, tetapi yang diambil
sekarang hanya data fase 1. Hambatan terbesar ternyata bukan cara mengambil
data, melainkan ketersediaannya. Rekapitulasi resmi tingkat kab/kota hanya ada
daring untuk DPR RI 2019; selebihnya harus diminta lewat PPID (lihat
`docs/data-inventory.md`).

## 1. Selisih dengan REVISI-v1.1 (yang berlaku)

| Topik | Dokumen kebutuhan v1.0 | REVISI-v1.1 | Penanganan |
| --- | --- | --- | --- |
| Kontestasi P0 | DPR RI, DPRD Provinsi, DPRD kab/kota, Pilpres, Pilkada 2020 dan 2024 | Pilpres, DPR RI, DPRD Provinsi 2019 dan 2024 | DPRD kab/kota dan Pilkada dicatat di inventaris sebagai fase 2 |
| Kedalaman wilayah | Sampai desa/kelurahan dan TPS bila tersedia | Sampai kecamatan | Tidak mengumpulkan desa atau TPS |
| Demografi BPS | P0/P1, masuk Tahap 1 butir 8 | Fase 2, lewat BPS WebAPI | Template `demografi_bps.csv` disiapkan, belum diisi |
| Kandidat, kursi, kepala daerah | P1, dengan `candidate_id` dan `seats_won` | Ditunda; skema hanya punya paslon Pilpres | Tidak dikumpulkan |
| Cara mengambil data | API, unduh, scraping HTML, Playwright | Unduh dan impor manual, sekali; Scrapy dan Playwright dicabut; hanya BPS WebAPI yang terjadwal | Pengambilan kali ini memakai skrip sekali jalan, tanpa scraper terjadwal |
| Survei | Metadata studi lengkap, 17 kolom | Agregat saja (fase 2), mikrodata tetap di NAS | Template `survei_agregat.csv` mengikuti v1.1, ditambah tanggal mulai/selesai dan klasifikasi |
| Media | Artikel, entitas, sentimen | Agregat bulanan dari aplikasi scraping internal; tidak ada tabel artikel | Template `media_agregat.csv` mengikuti v1.1 |
| Asisten AI riset | Tahap 3 | Di luar cakupan | Tidak dicatat |

## 2. Catatan teknis atas isi dokumen

Hal-hal berikut sebaiknya diselaraskan di versi berikutnya dokumen kebutuhan.

1. **`vote_share` disimpan** (variabel minimum bagian 4.2). Di sistem ini vote
   share selalu dihitung dari suara dan suara sah, tidak disimpan (`CLAUDE.md`,
   Formula).
2. **Status kualitas.** Dokumen memakai `unverified`, `in_review`, `validated`,
   `rejected`, `superseded`. Inventaris sumber memakai nilai yang sama. Database
   tetap memakai status versi dataset (`pending` sampai rekonsiliasi T3.3 lolos)
   dan `data_status` (`official`, `unofficial`, `internal_aggregate`).
3. **Nilai `NA`.** Sistem tidak menulis `NA`: angka tak tersedia diekspor sebagai
   sel kosong dengan kolom alasan (T5.4). Prinsip "kosong bukan nol" sama.
4. **Kode wilayah** sudah sesuai: teks, kode Kemendagri bertitik (`32.04.05`).
   KPU 2024 menulis tanpa titik (`320405`); konversinya ada di pipeline.
5. **Tabel batas terpisah** (`region_boundaries`). Di sistem ini geometri
   menempel di `regions` dengan `valid_from`/`valid_until`; edisi batas dicatat
   lewat sumber.
6. **Dapil tabel sendiri** sudah sesuai rencana T2.6 (template `dapil*.csv`).
7. **OCR.** Hampir semua formulir resmi berupa PDF hasil pindai. Camelot (di
   stack) hanya membaca PDF digital. Tesseract yang disebut dokumen belum ada di
   stack dan butuh persetujuan sebagai dependensi baru. Pilihan lainnya entri
   manual ganda (dua orang, lalu dibandingkan). Ini perlu diputuskan sebelum
   T3.2.
8. **Partisipasi** memang harus terpisah per kontestasi. Sumber pembanding
   Sirekap tidak memuat DPT maupun suara sah, jadi tidak bisa dipakai menghitung
   vote share.
9. **Etika pengambilan** (bagian 2.3) dipenuhi: `robots.txt` dicek, tidak ada
   login atau CAPTCHA yang dilewati, setiap permintaan diberi jeda.

## 3. Data pembanding

Pembanding dipakai untuk menguji angka, bukan untuk menggantikan rekapitulasi
resmi. Template `data/metadata/templates/rekonsiliasi.csv` mencatat hasil
setiap perbandingan.

| Pembanding | Dibandingkan dengan | Kegunaan | Batas |
| --- | --- | --- | --- |
| Salinan Sirekap 2024 di Internet Archive | Rekap resmi kab/kota dan kecamatan 2024 (setelah PPID) | Mendeteksi selisih besar; mencocokkan kode kecamatan KPU 2024 dengan kode BIG | Tidak resmi. Snapshot saat penghitungan berjalan, jadi setiap baris membawa progres TPS. Tanpa DPT dan suara sah. DPRD Provinsi hampir tidak terarsip |
| Open Data KPU (XLSX DD1-DPR 2019) | Pindaian Lampiran II Kpt 987 | XLSX bisa dibaca mesin, sedangkan pindaian adalah dokumen sah | XLSX adalah turunan; Dapil X tidak bisa diunduh (HTTP 500) |
| Lampiran III.12 Kpt 987 (DPD Jawa Barat) | DPT per kab/kota Pilpres dan DPR 2019 | DPT sama lintas kontestasi dalam satu pemilu | Pengguna hak pilih berbeda per kontestasi |
| Kpt KPU 1043/2024 (partisipasi) | Partisipasi hasil impor 2024 | Cek DPT dan pengguna di tingkat provinsi dan dapil | Tidak per kab/kota |
| Ringkasan PDF KPU Sumedang 2019 | DB1 Sumedang | PDF digital, siap dibaca | Bukan formulir bertanda tangan |
| Kode BIG 2026 | Kode kecamatan di Sirekap 2024 | Bahan awal padanan wilayah (T2.3) | Batas BIG adalah edisi 2026 |
| BPS Statistik Politik Jawa Barat 2019 | Rekap kab/kota 2019 | Mungkin satu-satunya angka Pilpres 2019 per kab/kota yang bisa didapat tanpa PPID | Isinya belum diperiksa |

Situng 2019 tidak bisa dipakai: servernya tidak tersambung, dan arsip Internet
Archive hanya berisi 38 URL tersebar.

### Isi salinan Sirekap 2024 yang terambil

Sirekap asli (`sirekap-obj-data.kpu.go.id`) sudah offline; yang terambil adalah
snapshot terakhir di Internet Archive. Turunannya ada di
`data/staging/sirekap-wayback-2024/`.

| Kontestasi | Per kab/kota (27) | Per kecamatan | TPS masuk saat snapshot |
| --- | --- | --- | --- |
| Pilpres | Snapshot 5 Mar 2024 | 627 kecamatan (27/27 kab/kota), snapshot 15 Feb–16 Mar 2024 | Kab/kota 106.595 dari 140.457 (75,9%); progres per kecamatan 9–100% |
| DPR RI | Snapshot 5 Mar 2024 | 540 kecamatan (25/27 kab/kota), snapshot 2 Mar–4 Apr 2024 | Kab/kota 85.743 dari 140.457 (61,0%) |
| DPRD Provinsi | Snapshot 3 Apr 2024 | 11 kecamatan (hanya Kota Depok) | Kab/kota 82.552 dari 140.457 (58,8%) |

Ke-627 kode kecamatan di salinan Sirekap 2024 semuanya ada di kode BIG 2026.
Untuk 2024, padanan kode KPU dengan referensi BIG adalah 1:1. Padanan 2019
masih harus dicek dari dokumen 2019.

## 4. Yang sudah diambil

Semua salinan mentah ada di `data/raw/` (tidak masuk Git; disalin ke NAS sesuai
T1.2) dan tercatat dengan SHA-256 di `data/raw/MANIFEST.csv`.

| Sumber | Isi | Skrip |
| --- | --- | --- |
| BIG, Batas Wilayah Administrasi edisi Juni 2026 | Batas 27 kab/kota dan 628 poligon kecamatan Jawa Barat, resolusi penuh (96 MB) dan tergeneralisasi | `pipeline/extract/big_wilayah.py` |
| KPU RI, JDIH dan Open Data | Kpt 987/2019 dan lampiran I, II.30 (Dapil X), III.12; DD1-DPR 2019 XLSX 10 dapil; Open Data Pilpres 2019 dan partisipasi; Kpt 360/2024, Lamp. V.12 (DPRD Prov Jabar), Kpt 1043/2024 | `pipeline/extract/kpu_dokumen.py` |
| KPU Kab. Sumedang | Ringkasan hasil 2019 per kecamatan untuk tiga kontestasi | `pipeline/extract/kpu_dokumen.py` |
| Internet Archive (Sirekap 2024) | Hasil hitung Sirekap Jawa Barat per kab/kota dan per kecamatan, tidak resmi | `pipeline/extract/sirekap_wayback.py` |

Turunan yang masuk Git: `data/reference/kode_wilayah_jabar.csv` dan
`batas_wilayah_{kabkota,kecamatan}_jabar.geojson` (T1.3, T1.4), serta
`data/metadata/` (inventaris, kamus data, template). Turunan pembanding Sirekap
ada di `data/staging/` dan sengaja tidak masuk Git.

## 5. Keputusan yang dibutuhkan

1. **Gerbang 1.** Dokumen kecamatan resmi daring hanya ada untuk 1–2 dari 27
   kab/kota. Ambang belum disepakati, dan angka akhirnya baru bisa dihitung
   setelah permohonan PPID dijawab.
2. **Permohonan PPID**: siapa yang mengajukan ke KPU Provinsi Jawa Barat dan ke
   KPU kab/kota, dan apa saja yang diminta (daftar di `docs/data-inventory.md`).
3. **OCR atau entri manual** untuk formulir hasil pindai (catatan teknis 7).
4. **Pembanding Sirekap**: saat ini hanya disimpan. Boleh tidaknya ditampilkan
   berlabel tidak resmi masih keputusan terbuka v1.1.
5. **Lisensi batas BIG di repo publik.** Berkas tergeneralisasi masuk Git dengan
   atribusi BIG. Ketentuan penggunaannya perlu dipastikan; bila tidak boleh
   disebarkan ulang, berkas itu dikeluarkan dari Git dan cukup disimpan di NAS.
