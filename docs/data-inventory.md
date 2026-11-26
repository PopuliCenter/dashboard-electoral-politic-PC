# Inventaris data fase 1 (T1.1)

Per 26 November 2026. Rincian per dokumen (URL halaman dan berkas, format, nomor
keputusan, lokasi salinan) ada di `data/metadata/source_inventory.csv`; kolom
`dataset_id` di tabel ini merujuk ke sana. Semua URL sudah dicek pada tanggal
itu.

**Hasil utama:** dokumen rekapitulasi resmi yang bisa diunduh daring hanya
lengkap untuk **DPR RI 2019 tingkat kab/kota**. Lima kontestasi lain hanya
tersedia per provinsi atau per dapil. Tingkat kecamatan resmi hanya ditemukan
untuk 1–2 dari 27 kab/kota. Sisanya harus diminta lewat PPID KPU Provinsi Jawa
Barat dan KPU kab/kota.

## Ketersediaan per kontestasi, tahun, dan tingkat

"Resmi" = rekapitulasi KPU yang ditetapkan. "Pembanding" = tidak resmi, hanya
untuk dibandingkan (REVISI-v1.1 bagian 3).

| Kontestasi | Tahun | Provinsi / dapil | Kabupaten/kota | Kecamatan |
| --- | --- | --- | --- | --- |
| Pilpres | 2019 | Resmi: Lamp. I Kpt 987 (pindaian) dan Open Data XLSX; partisipasi CSV (`KPU-2019-KPT987-L1`, `KPU-OD-140`, `KPU-OD-106`) | **Tidak ada resmi daring** (DC1-PPWP KPU Jabar, perlu PPID). Pembanding: tabel BPS Jabar 27 kab/kota, ada salah ketik (`BPS-STATPOL-JABAR-2019`) | Kota Bogor DB1 **diarsipkan** (pindaian); Sumedang hanya ringkasan PDF. Pembanding: peta GIS Kab. Bogor 40 kecamatan, persentase saja (`KPU-BOGORKAB-2019-GIS`) |
| DPR RI | 2019 | Resmi per dapil, dengan partisipasi (`KPU-OD-86`) | **Resmi, 27/27**: DD1-DPR Open Data XLSX untuk 10 dapil (23 kab/kota) dan pindaian Lamp. II.30 untuk Dapil X (Ciamis, Kuningan, Pangandaran, Kota Banjar); memuat partisipasi | Kota Bogor dan Sumedang DB1 **diarsipkan** (pindaian). Pembanding: peta GIS Kab. Bogor |
| DPRD Provinsi | 2019 | **Tidak ada daring**: keputusan hasil KPU Jabar tidak ada di JDIH; berkas Kpt 87 rusak | Tidak ada | Kota Bogor dan Sumedang DB1 **diarsipkan** (pindaian). Pembanding: peta GIS Kab. Bogor |
| Pilpres | 2024 | Resmi: **Kpt 360 Lamp. I diarsipkan** (suara paslon per provinsi; Jawa Barat suara sah 28.726.523, `KPU-2024-KPT360-L1`); partisipasi Kpt 1043. Partisipasi Jawa Barat juga dikutip BPS Jabar dari KPU (`BPS-STATPOL-JABAR-2024`). Pembanding: tabel statistik BPS per provinsi, cocok 39/39 (`SEKUNDER-PILPRES-PROVINSI-2004-2024`) | **Tidak ada resmi daring.** Kab. Indramayu dari D.HASIL KABKO (diserahkan pengguna). Pembanding: salinan Sirekap 27/27 | Kota Bogor D.HASIL **diarsipkan** (pindaian); **Kab. Indramayu D.HASIL KABKO, 31 kecamatan, sudah diekstrak**. Pembanding: Sirekap 27/27 kab/kota |
| DPR RI | 2024 | Resmi per dapil: **Kpt 360 Lamp. III diarsipkan** (suara partai dan caleg per dapil, PDF digital; Jawa Barat halaman 158–250, `KPU-2024-KPT360-L3`) dan **Lamp. II diarsipkan** (suara partai per dapil saja, 7 lembar, `KPU-2024-KPT360-L2`); partisipasi per dapil Kpt 1043 | **Tidak ada resmi daring.** Kab. Indramayu dari D.HASIL KABKO. Pembanding: salinan Sirekap | Kota Bogor D.HASIL **diarsipkan** (pindaian); **Kab. Indramayu, 31 kecamatan, sudah diekstrak**. Pembanding: Sirekap 25/27 kab/kota |
| DPRD Provinsi | 2024 | Resmi per dapil (15 dapil): Kpt KPU Jabar 13/2024, tanpa partisipasi | **Tidak ada resmi daring.** Kab. Indramayu dari D.HASIL KABKO. Pembanding: salinan Sirekap (tingkat provinsi, per kab/kota) | Kota Bogor D.HASIL **diarsipkan** (pindaian); **Kab. Indramayu, 31 kecamatan, sudah diekstrak**. Pembanding: Sirekap 1/27 kab/kota |

Kode dan batas wilayah: lengkap dari BIG edisi Juni 2026, 27 kab/kota dan 627
kecamatan (`BIG-BATAS_*`). Lihat `data/reference/README.md`.

## Letak arsip data mentah

Semua dokumen mentah ada di `data/raw/` (lihat `data/raw/MANIFEST.csv`). Folder
ini tidak masuk Git dan tidak ikut di-push ke GitHub; yang dilacak hanya
`MANIFEST.csv`.

Di laptop pengelola ada juga folder **`data mentah`** di akar proyek. Itu
pintasan (junction Windows) ke `data/raw/`, bukan salinan: isinya sama persis
dan tidak memakan ruang tambahan. Folder ini juga diabaikan Git.

- **Membuat ulang pintasan** (PowerShell, dari akar proyek):
  `New-Item -ItemType Junction -Path "data mentah" -Target "data\raw"`
- **Menghapus pintasan saja:** `cmd /c rmdir "data mentah"`. Jangan pakai
  `Remove-Item -Recurse` atau menghapus isinya dari dalam folder, karena itu
  menghapus berkas asli di `data/raw/`.
- **Menyalin ke NAS atau cadangan:** salin `data/raw/` saja, supaya berkas
  tidak tersalin dua kali.

## Dampak ke Gerbang 1

Gerbang 1 menghitung persentase kecamatan yang punya rekapitulasi resmi.
Berdasarkan dokumen yang tersedia daring hari ini:

- 2019: dokumen kecamatan resmi untuk 2 dari 27 kab/kota (Kota Bogor 6
  kecamatan; Sumedang 26 kecamatan, DPR dan DPRD Provinsi saja).
- 2024: 2 dari 27 kab/kota: Kota Bogor (6 kecamatan, Google Drive) dan
  Kabupaten Indramayu (31 kecamatan, diserahkan pengguna 26 November 2026,
  `KPU-INDRAMAYU-2024-*`).

Angka ini batas bawah: permohonan PPID belum diajukan. Ambang Gerbang 1 masih
keputusan terbuka; angka akhirnya dihitung setelah permohonan PPID dijawab.

### Penelusuran situs PPID KPU kab/kota (26 November 2026)

Ke-27 situs `<kab/kota>ppid.kpu.go.id` dibuka lewat Chrome, dan semua halaman
daftar Informasi Berkala, Serta Merta, dan Setiap Saat ditelusuri (bukan hanya
halaman pertama). Pemindai diuji dulu pada situs Kota Bogor, yang memang memuat
dokumen, dan menemukannya.

- **Dokumen kecamatan resmi Pilpres/DPR RI/DPRD Provinsi hanya ada di Kota
  Bogor (2019 dan 2024) dan Sumedang (2019).** Keduanya sudah diarsipkan.
- **Kab. Bogor:** peta GIS 2019 per kecamatan, diarsipkan sebagai pembanding.
- **Hanya DPRD kabupaten atau Pilkada (fase 2):** Kab. Bandung, Ciamis,
  Purwakarta, Tasikmalaya.
- **Tidak ada dokumen hasil 2019/2024:** 19 situs lainnya.

Jadi angka Gerbang 1 di atas tidak berubah: sisanya tetap harus diminta lewat
PPID. Purwakarta menautkan JDIH KPU per kab/kota
(`jdih.kpu.go.id/jabar/<kab>/kepkpukabkot`); isinya keputusan KPU kab/kota,
kebanyakan DPRD kabupaten, dan belum ditelusuri per daerah.

### Kabupaten Indramayu 2024

Dua belas dokumen KPU Kab. Indramayu (berita acara rekapitulasi kabupaten dan
SK 67/70 Tahun 2024) diarsipkan di `data/raw/kpu-indramayu/2024/`, beserta
workbook ekstraksi OCR-nya di subfolder `ekstraksi/`. Untuk Pilpres, DPR RI,
dan DPRD Provinsi, workbook memuat suara per kecamatan dan partisipasi.

Ekstraksi lolos uji ulang: nama 31 kecamatan cocok dengan kode BIG, suara
peserta sama dengan suara sah, dan total sama dengan dokumen. Total suara sah:
Pilpres 1.021.836, DPR RI 914.655, DPRD Provinsi 885.643. Masih perlu:

- URL atau asal unduhan dokumen dicatat (sekarang "diserahkan pengguna");
- konversi ke format impor (T3.2) dan rekonsiliasi (T3.3) sebelum dimuat.

DPD dan DPRD kabupaten di dokumen yang sama di luar cakupan fase 1.

## Yang perlu dikerjakan manusia

1. **Permohonan PPID ke KPU Provinsi Jawa Barat**: DC1/DD1-PPWP dan hasil DPRD
   Provinsi 2019 per kab/kota; D.HASIL PROVINSI 2024 untuk Pilpres, DPR RI, dan
   DPRD Provinsi.
2. **Permohonan PPID ke KPU kab/kota** (25–26 daerah): DB1 2019 dan D.HASIL
   KABKO 2024, untuk tingkat kecamatan.
3. **Entri manual atau OCR** untuk dokumen pindaian yang sudah diarsipkan:
   Kota Bogor (DB1 2019, D.HASIL 2024) dan Sumedang (DB1 2019), lihat
   `data/raw/kpu-kotabogor/` dan `data/raw/kpu-sumedang/`. Keputusan
   OCR atau entri manual ganda masih terbuka (`docs/review-kebutuhan-data.md`).
   Dokumen baru dari luar skrip diarsipkan dengan
   `python pipeline/extract/arsip_lokal.py BERKAS... --dest data/raw/<sumber>/<tahun> --source "..." --origin "<URL>"`.
4. **Salin `data/raw/` ke NAS** (T1.2).
5. **Verifikasi** kode wilayah dan isi Lampiran IV Kpt 360. Lampiran I
   (Pilpres per provinsi), II (suara partai DPR per dapil), dan III (suara
   partai dan caleg DPR per dapil) sudah dipastikan. Lampiran IV belum
   terunduh karena Chrome menahan unduhan kedua dari situs JDIH: izinkan
   "unduhan ganda" untuk `jdih.kpu.go.id` di Chrome bila ingin diambil.
6. **Data dicicil pengguna** (26 November 2026): Lampiran III Kpt 360
   (DPR RI per dapil), lalu Lampiran I (Pilpres per provinsi), keduanya identik
   dengan berkas JDIH; lalu tabel Pilpres per provinsi 2004–2024. Tabel itu
   ternyata tabel statistik BPS: isinya identik byte demi byte dengan unduhan
   dari halaman BPS. Tabel itu **tidak memuat 2019** meski disebut di nama
   berkasnya, jadi Pilpres 2019 per provinsi tetap dari Lampiran I Kpt 987 dan
   Open Data KPU. Rincian per kab/kota dan kecamatan tetap membutuhkan D.HASIL
   tingkat provinsi dan kab/kota.

## Data BPS di luar cakupan fase 1

Diminta pengguna 26 November 2026 dari subjek BPS "Aktivitas Politik dan
Komunitas Lainnya" (subjek 528). Datanya **hanya diarsipkan dan
diinventarisasi**: tidak dimuat ke database dan tidak dipakai fitur fase 1.
Berkasnya disimpan di `data/raw/bps/` (25 berkas):

- 23 berkas diunduh sebagai XLSX lewat tombol Unduh di situs BPS, satu berkas
  per tahun.
- 2 tabel XLS nasional diunduh pengguna; isinya identik dengan unduhan
  langsung dari halaman BPS.

| Data | Tahun | Tingkat | `dataset_id` |
| --- | --- | --- | --- |
| Anggota DPD menurut jenis kelamin | 2009, 2014, 2019, 2024 | provinsi | `BPS-DPD-JENIS-KELAMIN-2009-2024` |
| Jumlah pemilih | 2004, 2009, 2014, 2019, 2024 | provinsi dan luar negeri | `BPS-JUMLAH-PEMILIH-2004-2024` |
| Indeks Demokrasi Indonesia, Metode Baru | 2021–2025 | provinsi | `BPS-IDI-MB-PROVINSI-2021-2025` |
| Indeks Demokrasi Indonesia, Metode Baru | 2021–2025 | nasional, pusat, provinsi | `BPS-IDI-MB-NASIONAL-2021-2025` |
| Indeks Demokrasi Indonesia, metode lama | 2020 saja | provinsi | `BPS-IDI-LAMA-PROVINSI-2020` |
| Indeks Hak Asasi Manusia: indeks, dimensi, hak sipil-politik | 2024 saja | nasional | `BPS-IHAM-2024` |
| Suara dan kursi DPR per partai (diunduh pengguna) | 2009, 2014, 2019, 2024 | nasional | `BPS-DPR-PARTAI-2009-2024` |
| Suara sah partai pemilu legislatif (diunduh pengguna) | 1955–2024, 13 pemilu | nasional | `BPS-PEMILU-LEGISLATIF-1955-2024` |

Hasil pengecekan:

- Tahun di dalam setiap berkas sesuai namanya, dan tidak ada dua berkas yang
  isinya sama.
- Untuk DPD dan jumlah pemilih, jumlah semua provinsi sama dengan baris
  INDONESIA.
- Angka yang dicocokkan dengan halaman BPS sama.

Catatan pemakaian:

- **IDI punya patahan metode.** Metode Baru (2021–2025) dan metode lama (2020)
  tidak boleh digabung jadi satu deret.
- **Seri IDI metode lama tidak lengkap.** Halaman metode lama di BPS hanya
  menyajikan 2020; deret sebelumnya tidak ada di daftar subjek 528.
- **Indeks HAM baru satu tahun (2024)** dan tidak ada rinciannya per provinsi.
- **Definisi "jumlah pemilih" tidak disebut di tabelnya.** Tabel menyebut KPU
  sebagai sumber, tetapi tidak menyatakan apakah angkanya DPT, dan tidak
  membedakan kontestasi. Untuk Jawa Barat 2024, angkanya (35.714.901) sama
  dengan DPT yang dikutip publikasi BPS Jabar (`BPS-STATPOL-JABAR-2024`). Tahun
  lain belum dicek. Jangan dipakai sebagai `registered_voters` sebelum
  dicocokkan dengan keputusan KPU.
- **Otomatisasi butuh kunci WebAPI BPS.** Tombol JSON di situs hanya
  menunjukkan endpoint WebAPI yang memerlukan kunci pribadi (fase 2,
  `BPS-WEBAPI`).
