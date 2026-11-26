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
| Pilpres | 2019 | Resmi: Lamp. I Kpt 987 (pindaian) dan Open Data XLSX; partisipasi CSV (`KPU-2019-KPT987-L1`, `KPU-OD-140`, `KPU-OD-106`) | **Tidak ada daring** (DC1-PPWP KPU Jabar, perlu PPID) | Kota Bogor DB1 (Drive, pindaian); Sumedang hanya ringkasan PDF |
| DPR RI | 2019 | Resmi per dapil, dengan partisipasi (`KPU-OD-86`) | **Resmi, 27/27**: DD1-DPR Open Data XLSX untuk 10 dapil (23 kab/kota) dan pindaian Lamp. II.30 untuk Dapil X (Ciamis, Kuningan, Pangandaran, Kota Banjar); memuat partisipasi | Kota Bogor dan Sumedang DB1 (Drive) |
| DPRD Provinsi | 2019 | **Tidak ada daring**: keputusan hasil KPU Jabar tidak ada di JDIH; berkas Kpt 87 rusak | Tidak ada | Kota Bogor dan Sumedang DB1 (Drive) |
| Pilpres | 2024 | Resmi: Kpt 360 Lamp. I (pemetaan lampiran belum terverifikasi); partisipasi Kpt 1043 | **Tidak ada resmi daring**. Pembanding: salinan Sirekap 27/27 | Kota Bogor D.HASIL (Drive). Pembanding: Sirekap 27/27 kab/kota |
| DPR RI | 2024 | Resmi per dapil: Kpt 360 Lamp. II (belum terverifikasi); partisipasi per dapil Kpt 1043 | **Tidak ada resmi daring**. Pembanding: salinan Sirekap | Kota Bogor D.HASIL (Drive). Pembanding: Sirekap 25/27 kab/kota |
| DPRD Provinsi | 2024 | Resmi per dapil (15 dapil): Kpt KPU Jabar 13/2024, tanpa partisipasi | **Tidak ada resmi daring**. Pembanding: salinan Sirekap (tingkat provinsi, per kab/kota) | Kota Bogor D.HASIL (Drive). Pembanding: Sirekap 1/27 kab/kota |

Kode dan batas wilayah: lengkap dari BIG edisi Juni 2026, 27 kab/kota dan 627
kecamatan (`BIG-BATAS_*`). Lihat `data/reference/README.md`.

## Dampak ke Gerbang 1

Gerbang 1 menghitung persentase kecamatan yang punya rekapitulasi resmi.
Berdasarkan dokumen yang tersedia daring hari ini:

- 2019: dokumen kecamatan resmi untuk 2 dari 27 kab/kota (Kota Bogor 6
  kecamatan; Sumedang 26 kecamatan, DPR dan DPRD Provinsi saja).
- 2024: 1 dari 27 kab/kota (Kota Bogor).

Angka ini batas bawah: situs utama KPU kab/kota tidak punya indeks dokumen, dan
permohonan PPID belum diajukan. Ambang Gerbang 1 masih keputusan terbuka; angka
akhirnya dihitung setelah permohonan PPID dijawab.

## Yang perlu dikerjakan manusia

1. **Permohonan PPID ke KPU Provinsi Jawa Barat**: DC1/DD1-PPWP dan hasil DPRD
   Provinsi 2019 per kab/kota; D.HASIL PROVINSI 2024 untuk Pilpres, DPR RI, dan
   DPRD Provinsi.
2. **Permohonan PPID ke KPU kab/kota** (25–26 daerah): DB1 2019 dan D.HASIL
   KABKO 2024, untuk tingkat kecamatan.
3. **Unduh manual dari Google Drive**: dokumen Kota Bogor (2019 dan 2024) dan
   Sumedang (2019) yang tercantum di inventaris.
4. **Salin `data/raw/` ke NAS** (T1.2).
5. **Verifikasi** kode wilayah dan isi Lampiran I–IV Kpt 360 (keempat berkas
   tampak sama di bagian awalnya; isi per berkas belum dipastikan).
