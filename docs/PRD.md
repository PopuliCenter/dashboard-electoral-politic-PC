# PRD — Populi Political & Electoral Intelligence Dashboard (v1.0)

> **Status:** dokumen asli v1.0, disimpan sebagai acuan. Cakupan aktif yang dikerjakan ada di `REVISI-v1.1.md`; bila keduanya berbeda, v1.1 yang berlaku.

- **Versi:** 1.0
- **Status:** Draft – Pilot Project
- **Organisasi:** Populi Center / Yayasan Populi Indonesia
- **Jenis Produk:** Web-based Political & Geospatial Intelligence Platform
- **Wilayah Pilot:** Provinsi Jawa Barat
- **Periode Data:** Pemilu 2019–2024 dan Pilkada 2020–2024

# BAGIAN I — PRODUCT REQUIREMENTS DOCUMENT (PRD)

## 1. Executive Summary

Populi Political & Electoral Intelligence Dashboard merupakan platform pengolahan, pemetaan, dan analisis data politik berbasis geospasial yang dikembangkan untuk mendukung kegiatan penelitian Populi Center.

Platform ini mengintegrasikan berbagai sumber data, meliputi:

- Hasil pemilihan umum.
- Hasil pemilihan kepala daerah.
- Kekuatan dan persebaran suara partai politik.
- Profil kandidat dan kepala daerah.
- Data kependudukan dan demografi.
- Indikator ekonomi dan pembangunan daerah.
- Kebijakan dan kinerja pemerintahan daerah.
- Data survei dan penelitian Populi Center.

Dashboard dirancang untuk membantu peneliti memahami dinamika politik secara spasial, historis, dan komparatif.

Sistem akan menggunakan pendekatan data-driven political intelligence, yaitu menggabungkan data resmi, data penelitian, dan data statistik untuk menghasilkan informasi yang dapat digunakan dalam analisis politik dan kebijakan publik.

## 2. Background & Problem Statement

Saat ini, data politik dan pemerintahan tersedia di berbagai instansi dan portal yang memiliki format, struktur, serta tingkat kedalaman berbeda.

Permasalahan utama:

1. Data hasil pemilu dan pilkada tersebar di berbagai sumber.
2. Data politik belum terintegrasi dengan data demografi dan ekonomi.
3. Perbandingan hasil elektoral antarperiode membutuhkan pengolahan manual.
4. Pemetaan kekuatan partai dan kandidat belum terpusat.
5. Informasi kepala daerah dan kebijakan publik belum terhubung dengan hasil elektoral.
6. Peneliti membutuhkan proses pengumpulan dan pembaruan data yang lebih efisien.

Solusi:

Membangun satu platform terintegrasi yang mampu mengumpulkan, mengolah, menyimpan, memvisualisasikan, dan menganalisis data politik serta pemerintahan daerah.

## 3. Product Objectives

**Tujuan utama**

1. Membangun database politik dan elektoral terintegrasi.
2. Menyediakan peta interaktif kekuatan partai dan kandidat.
3. Membandingkan hasil pemilu dan pilkada lintas periode.
4. Mengintegrasikan data demografi dan indikator pembangunan.
5. Menyediakan profil kepala daerah dan informasi kebijakan publik.
6. Mengurangi pekerjaan manual dalam pengumpulan dan pengolahan data.
7. Menyediakan fondasi pengembangan analisis statistik dan prediktif.

**Key Performance Indicators (KPI)**

| Indikator | Target pilot |
| --- | --- |
| Data wilayah terintegrasi | 100% wilayah administratif pilot |
| Dataset elektoral | Minimal Pemilu 2019 dan 2024 |
| Data Pilkada | Pilkada 2020 dan 2024 |
| Modul dashboard | Minimal 5 modul utama |
| Akurasi data | 100% lolos validasi terhadap angka sumber yang digunakan |
| Pembaruan data otomatis | Pipeline berjalan terjadwal |
| Waktu pemuatan peta | Target maksimal 5 detik pada kondisi pengujian yang ditetapkan |
| Data memiliki sumber | 100% dataset memiliki metadata sumber |
| Pengguna pilot | Admin dan peneliti Populi Center |

Catatan: KPI akurasi berlaku untuk data yang berhasil diperoleh dan diverifikasi. Kelengkapan data harus dilaporkan terpisah dari akurasi.

## 4. Target Users

#### A. Administrator

Memiliki kewenangan untuk:

- Mengelola pengguna.
- Mengelola database.
- Mengatur sumber data.
- Mengelola proses scraping.
- Memvalidasi dan menyetujui data.
- Mengelola konfigurasi sistem.

#### B. Researcher / Political Analyst

Dapat:

- Mengakses peta elektoral.
- Membandingkan hasil pemilu.
- Melihat kekuatan partai.
- Melihat profil kandidat dan kepala daerah.
- Menganalisis karakteristik wilayah.
- Mengunduh data dan laporan.

#### C. Data Analyst

Dapat:

- Mengakses dataset terstruktur.
- Melakukan filter dan agregasi.
- Membandingkan indikator.
- Mengekspor data CSV/XLSX.
- Memeriksa metadata dan kualitas data.

## 5. Product Scope

### 5.1 Modul Utama

| Modul | Deskripsi | Prioritas |
| --- | --- | --- |
| Overview Dashboard | Ringkasan kondisi politik dan elektoral | P0 |
| Electoral Mapping | Peta hasil pemilu dan pilkada | P0 |
| Political Party Intelligence | Analisis kekuatan partai | P0 |
| Election Comparison | Perbandingan hasil antarperiode | P0 |
| Regional Leader | Profil gubernur, bupati, wali kota | P1 |
| Demographic Intelligence | Data penduduk dan sosial ekonomi | P1 |
| Public Policy | Data kebijakan dan pembangunan | P1 |
| Candidate Intelligence | Profil dan rekam jejak kandidat | P1 |
| Data Management | Pengelolaan data dan scraping | P0 |
| Export & Reporting | Ekspor laporan dan dataset | P1 |
| AI Research Assistant | Ringkasan dan analisis berbantuan AI | P2 |

P0 = wajib tersedia untuk MVP.
P1 = pengembangan setelah MVP.
P2 = pengembangan lanjutan.

### 5.2 Modul Overview Dashboard

Halaman utama menampilkan:

- Total wilayah yang memiliki data.
- Jumlah partai politik.
- Jumlah kandidat.
- Hasil pemilu berdasarkan periode.
- Partai dengan perolehan suara tertinggi.
- Distribusi kemenangan kandidat.
- Ringkasan tren elektoral.
- Peta kekuatan politik Jawa Barat.

Filter global:

- Tahun pemilu.
- Jenis pemilihan.
- Provinsi.
- Kabupaten/kota.
- Kecamatan.
- Partai.
- Kandidat.

### 5.3 Modul Electoral Mapping

Modul ini merupakan fitur utama pilot project.

Fitur:

1. Interactive Map.
2. Choropleth Map.
3. Party Dominance Map.
4. Vote Share Map.
5. Candidate Winning Map.
6. Electoral Swing Map.
7. Turnout Map.
8. Detail data setiap wilayah.

Hierarki peta:

Provinsi → Kabupaten/Kota → Kecamatan → Desa/Kelurahan.

Detail yang ditampilkan saat pengguna memilih wilayah:

- Nama wilayah.
- Total suara sah.
- Jumlah pemilih dan pengguna hak pilih.
- Persentase partisipasi.
- Peringkat partai.
- Perolehan suara setiap partai.
- Perubahan suara dibandingkan pemilu sebelumnya.
- Kandidat pemenang jika relevan.

Catatan: Kedalaman data mengikuti ketersediaan data resmi. Jangan mengasumsikan semua hasil pemilu tersedia dalam satu tingkat administratif untuk setiap jenis pemilihan.

### 5.4 Modul Political Party Intelligence

Fitur:

- Profil partai.
- Identitas dan logo.
- Hasil suara per pemilu.
- Distribusi suara per kabupaten/kota.
- Jumlah kursi legislatif.
- Perubahan perolehan suara.
- Daerah dengan kekuatan elektoral tertinggi.
- Perbandingan antarpartai.

Indikator analisis:

**Vote Share**

Persentase suara partai dibandingkan total suara sah dalam kontestasi yang sama.

**Electoral Swing**

Perubahan persentase suara partai antarperiode.

**Party Ranking**

Peringkat partai berdasarkan jumlah suara atau persentase suara.

**Electoral Concentration**

Mengukur tingkat konsentrasi dukungan partai di wilayah tertentu.

### 5.5 Modul Candidate Intelligence

Informasi:

- Nama kandidat.
- Foto.
- Partai pengusung.
- Riwayat pencalonan.
- Riwayat jabatan.
- Wilayah kontestasi.
- Hasil pemilihan.
- Status petahana.
- Koalisi pendukung.

Seluruh informasi harus dilengkapi sumber dan tanggal pembaruan.

### 5.6 Modul Regional Leader

Informasi kepala daerah:

- Nama gubernur/bupati/wali kota.
- Periode jabatan.
- Wakil kepala daerah.
- Partai pengusung.
- Riwayat pemilihan.
- Program pemerintahan.
- Informasi kebijakan.
- Indikator pembangunan daerah.

### 5.7 Modul Demographic Intelligence

Indikator:

- Jumlah penduduk.
- Kelompok umur.
- Pendidikan.
- Jenis pekerjaan.
- Kepadatan penduduk.
- Tingkat kemiskinan.
- Tingkat pengangguran.
- Pertumbuhan ekonomi.
- Indeks Pembangunan Manusia.

Sumber utama: BPS dan portal data pemerintah.

### 5.8 Modul Public Policy Intelligence

Data:

- APBD.
- Pendapatan daerah.
- Belanja daerah.
- Infrastruktur.
- Pendidikan.
- Kesehatan.
- Kemiskinan.
- Pengangguran.
- Program prioritas pemerintah.

Fitur:

- Perbandingan indikator antarwilayah.
- Tren pembangunan.
- Perbandingan anggaran dan indikator hasil.
- Monitoring perubahan kebijakan.

Analisis anggaran harus membedakan pagu, realisasi, dan tahun anggaran.

## 6. User Stories

| ID | User Story | Acceptance Criteria |
| --- | --- | --- |
| US-01 | Sebagai peneliti, saya ingin melihat peta kekuatan partai | Peta menampilkan partai dominan berdasarkan filter |
| US-02 | Saya ingin membandingkan Pemilu 2019 dan 2024 | Perubahan suara dapat ditampilkan |
| US-03 | Saya ingin memilih kabupaten | Peta dapat melakukan drill-down |
| US-04 | Saya ingin melihat profil kandidat | Informasi kandidat dan sumber data tampil |
| US-05 | Saya ingin mengunduh data | Data dapat diekspor CSV/XLSX |
| US-06 | Saya ingin melihat tren demografi | Grafik menampilkan data berdasarkan tahun |
| US-07 | Saya ingin mengelola sumber data | Admin dapat menambah sumber |
| US-08 | Saya ingin memperbarui database | Admin dapat menjalankan pipeline |
| US-09 | Saya ingin memeriksa validitas data | Sistem menampilkan status validasi |
| US-10 | Saya ingin melihat riwayat pembaruan | Sistem menyimpan log perubahan |

## 7. Non-Functional Requirements

| Kategori | Requirement |
| --- | --- |
| Performance | Pemuatan dashboard ditargetkan maksimal 5 detik |
| Scalability | Dapat diperluas ke 38 provinsi |
| Security | Login dan role-based access control |
| Availability | Target uptime 99,5% pada tahap produksi |
| Responsive | Desktop, tablet, dan mobile |
| Data Integrity | Validasi dan audit perubahan data |
| Maintainability | Backend dan frontend terpisah |
| Backup | Backup database terjadwal |
| Privacy | Pembatasan akses data sensitif |
| Traceability | Setiap dataset memiliki sumber dan versi |

## 8. Out of Scope MVP

Tidak termasuk dalam pilot pertama:

- Prediksi hasil pemilu secara otomatis.
- Analisis preferensi politik individu.
- Pelacakan individu berdasarkan pilihan politik.
- Pemantauan media sosial secara masif.
- Integrasi seluruh kabupaten/kota Indonesia.
- Model AI untuk rekomendasi strategi kampanye.
- Aplikasi mobile native.

Fokus MVP adalah data historis, pemetaan, dan analisis deskriptif.

## 9. Product Acceptance Criteria

Pilot dinyatakan berhasil apabila:

1. Pengguna dapat login.
2. Peta Jawa Barat dapat ditampilkan.
3. Pengguna dapat memilih periode pemilu.
4. Pengguna dapat melihat distribusi suara partai.
5. Pengguna dapat membandingkan hasil pemilu 2019 dan 2024 pada unit wilayah yang sebanding.
6. Pengguna dapat melihat detail hasil berdasarkan wilayah.
7. Pengguna dapat mengakses profil partai.
8. Data memiliki sumber dan metadata.
9. Administrator dapat melakukan import dan validasi data.
10. Pengguna dapat mengekspor hasil analisis.
