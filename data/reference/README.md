# data/reference

Berkas acuan yang boleh masuk Git karena kecil dan tidak mengandung data individu.

| Berkas | Isi | Tugas | Status |
| --- | --- | --- | --- |
| `parties.csv` | Partai nasional peserta Pemilu 2019 dan 2024, dengan nomor urut per pemilu | T2.5 | Terisi, **menunggu verifikasi peneliti** |
| `elections.csv` | Enam kontestasi fase 1: Pilpres, DPR RI, DPRD Provinsi, masing-masing 2019 dan 2024 | T2.5 | Terisi, **menunggu verifikasi peneliti** |
| `candidate_pairs.csv` | Pasangan calon presiden dan wakil presiden, dengan nomor urut | T2.5 | Terisi, **menunggu verifikasi peneliti** |
| `party_colors.csv` | Warna partai `#RRGGBB` dari identitas visual resmi, dengan sumber | T4.5 | Kolom warna **kosong**; selama kosong peta memakai warna cadangan bertanda |
| `kode_wilayah_jabar.csv` | Kode Kemendagri: provinsi, 27 kabupaten/kota, kecamatan | T1.3 | Belum ada |
| `batas_wilayah_*.geojson` | Batas wilayah kab/kota dan kecamatan, dengan sumber dan tahun versi | T1.4 | Belum ada |

## Memasukkan ke database

```
make seed-dry     # validasi dan tampilkan apa yang akan berubah, tanpa menulis
make seed         # tulis
```

Windows: `.\make.ps1 seed-dry` lalu `.\make.ps1 seed`.

Seed aman dijalankan berulang kali. Ia tidak pernah menghapus: partai atau paslon
yang ada di database tetapi tidak ada di CSV dilaporkan sebagai peringatan dan
dibiarkan. Setiap jalan tercatat di tabel `audit_logs` beserta checksum SHA-256
ketiga berkas.

## Verifikasi oleh peneliti (wajib sebelum produksi)

Isi berkas T2.5 disusun dari riset sumber publik dan diperiksa silang, tetapi
**belum dicocokkan oleh manusia dengan dokumen KPU**. Kolom `verified_by` sengaja
kosong; tidak boleh diisi oleh siapa pun selain peneliti yang benar-benar
memeriksa.

Di lingkungan `production`, seed **menolak berjalan** selama masih ada satu baris
dengan `verified_by` kosong. Di pengembangan hanya muncul peringatan.

Langkah verifikasi:

1. Buka Keputusan KPU tentang nomor urut partai politik peserta pemilu, untuk
   2019 dan 2024 (nomornya tercatat di `docs/decisions.md`).
2. Untuk setiap baris di `parties.csv`, cocokkan nomor urut, nama resmi, dan
   singkatan. Periksa juga tautan di `source_2019` dan `source_2024` masih hidup;
   bila tidak, ganti dengan salinan arsip dokumen di `data/raw/`.
3. Lakukan hal yang sama untuk tanggal pemungutan suara di `elections.csv` dan
   nama paslon di `candidate_pairs.csv`.
4. Isi `verified_by` dengan inisial pemeriksa pada setiap baris yang sudah cocok.
   Baris yang salah: perbaiki nilainya dan catat alasannya di kolom `notes`
   (khusus `parties.csv`) atau di pesan commit.
5. Jalankan `make seed-dry` dan pastikan tidak ada kesalahan.

### Yang sudah diperiksa silang, dan yang belum

Pada 20 November 2026 isi ketiga berkas diperiksa silang lewat tiga jalur riset
yang saling terpisah (dokumen KPU, liputan pengundian nomor urut, ensiklopedia
berikut rujukannya). Hasilnya:

- **Nomor urut dan keikutsertaan: sepakat di ketiga jalur**, untuk 16 partai
  nasional 2019 dan 18 partai nasional 2024. Tidak ada satu nomor pun yang
  diperselisihkan.
- Tanggal pemungutan suara dan nomor urut paslon: sepakat.

Itu pemeriksaan silang antar sumber publik, **bukan pengganti verifikasi
peneliti**. Titik yang paling perlu dilihat langsung di dokumen aslinya:

| Hal | Mengapa perlu dilihat |
| --- | --- |
| Lampiran SK 519/2022 (nomor urut 2024) | Tidak berhasil dibuka (JDIH KPU berulang kali tidak merespons). Nomor 1 sampai 24 dibaca dari Lampiran SK 552/2022, yang memuat ulang seluruh tabel, dan cocok dengan tiga situs KPU daerah |
| SK 59, 81, 310 Tahun 2018 (nomor urut 2019) | Dibaca dari salinan pindaian di situs Mahkamah Konstitusi, bukan dari JDIH KPU |
| Ejaan "Sandiaga Salahuddin Uno" | Mengikuti transkripsi SK 1142/2018 di situs pihak ketiga; risalah MK menulis "Salahudin". PDF asli SK belum terbaca |
| Lampiran SK 1644/2023 (paslon 2024) | Belum terbaca. Nama diambil dari KPU Info Pemilu; putusan MK hanya menguatkan paslon 1 dan 2 |
| Tanggal 17 April 2019 | Dari Lampiran PKPU 7/2017. PKPU itu kemudian diubah (antara lain PKPU 32/2018) dan jadwal perubahannya belum dibaca; tanggalnya dikuatkan risalah MK |

Nama paslon ditulis seperti KPU menulisnya, tanpa gelar: "A. Muhaimin Iskandar"
dan "M. Mahfud MD", bukan kepanjangannya. "MD" bagian dari nama, bukan gelar.

### Nama partai berbeda antar dokumen KPU

KPU sendiri tidak konsisten menulis nama partai. Kolom `notes` di `parties.csv`
mencatat varian yang ditemukan, misalnya "Partai Golkar" dan "Partai Golongan
Karya", atau "Partai PERINDO" dan "Partai Persatuan Indonesia". Karena itu
ekstraktor (T3.2) mencocokkan partai lewat **nomor urut**, tidak lewat nama.

## Aturan menyunting

- Simpan dari Excel sebagai **CSV UTF-8 (Comma delimited)**. Format lain membuat
  huruf beraksen dan tanda kutip lengkung rusak; seed akan menolaknya dengan
  pesan yang menjelaskan caranya. Pemisah titik koma (bawaan Excel berlokal
  Indonesia) diterima.
- `ballot_number_<tahun>` kosong berarti partai **tidak ikut** pemilu tahun itu.
  Itu satu-satunya cara menandai keikutsertaan; tidak ada kolom terpisah.
- Partai yang ikut pemilu wajib punya `source_<tahun>`. Tidak ada angka tanpa sumber.
- `party_code` adalah identitas tetap di sistem. Jangan diganti setelah ada hasil
  pemilu yang merujuknya, bahkan bila partainya berganti nama: ganti `party_name`
  saja, dan catat nama lama di `notes`.
- Partai lokal Aceh tidak dimasukkan: fase 1 hanya Jawa Barat. Itu sebabnya
  nomor urut nasional punya celah (2019: 15 sampai 18; 2024: 18 sampai 23).
