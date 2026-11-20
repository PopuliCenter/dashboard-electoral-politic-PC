# Format impor baku (T3.1)

Semua hasil pemilu masuk lewat CSV berformat baku ini, baik yang diketik tangan
maupun hasil ekstraktor PDF/Excel (T3.2). Validatornya ada di
`backend/app/importer/`; berkas yang gagal validasi tidak boleh dimuat ke
staging maupun produksi.

## Aturan umum

- **Satu berkas = satu kontestasi = satu `data_status`.** Misalnya "DPR RI 2024,
  resmi". Berkas yang mencampur Pilpres dengan DPR, 2019 dengan 2024, atau data
  resmi dengan tidak resmi ditolak. Satu berkas nanti menjadi satu versi dataset
  dengan satu sumber (T3.4).
- **Satu berkas = satu jenis data.** Jenisnya dikenali dari kolom: ada
  `party_code`, `pair_number`, atau `registered_voters`.
- Simpan sebagai **CSV UTF-8**. Pemisah koma atau titik koma (bawaan Excel
  berlokal Indonesia) sama-sama diterima. Urutan kolom bebas; kolom lain tidak
  boleh ada.
- **Angka**: bilangan bulat tanpa pemisah ribuan (`1234567`, bukan
  `1.234.567`), tidak negatif. Nol boleh. Hanya angka 0-9: tanda catatan kaki
  yang terbawa dari PDF (misalnya `120¹`) ditolak, hapus tandanya.
- **Setiap baris berisi semua kolom.** Baris yang kolomnya kurang ditolak, tidak
  dianggap "tidak tersedia": sel kosong harus tetap ada (`1000,,780,20`).
- **Angka yang tidak ada di dokumen sumber tidak boleh ditebak.** Untuk suara
  partai dan paslon, hapus barisnya; kekosongan itu akan terlihat di laporan
  kelengkapan (T3.5). Untuk partisipasi, biarkan selnya kosong.
- **Kode wilayah**: kode Kemendagri bertitik, dengan nol di depan:
  `32` (provinsi), `32.04` (kabupaten/kota), `32.04.05` (kecamatan). Hati-hati:
  Excel suka membuang nol di depan atau mengubah `32.10` menjadi `32.1`. Format
  kolomnya sebagai Teks sebelum mengetik. Kode harus berlaku pada hari
  pemungutan suara pemilu yang bersangkutan (lihat `valid_from`/`valid_until`
  di tabel `regions`).
- Satu wilayah boleh muncul di beberapa tingkat dalam satu berkas (kecamatan
  dan kabupaten/kotanya), tetapi tidak boleh dua kali untuk partai atau paslon
  yang sama.

Nilai `election_type`: `presidential`, `legislative_dpr`,
`legislative_dprd_province`. Nilai `data_status`: `official` (rekapitulasi KPU)
atau `unofficial` (misalnya Sirekap). `internal_aggregate` ditolak: status itu
untuk agregat media dan survei, bukan hasil pemilu.

## 1. Suara partai (DPR RI, DPRD Provinsi)

| Kolom | Isi |
| --- | --- |
| `election_type` | `legislative_dpr` atau `legislative_dprd_province` |
| `election_year` | `2019` atau `2024` |
| `region_code` | Kode Kemendagri |
| `party_code` | Dari `data/reference/parties.csv`, misal `PKB`. Partai harus ikut pemilu tahun itu |
| `vote_count` | Suara partai (termasuk suara calegnya), bilangan bulat |
| `data_status` | `official`, dst. |

```csv
election_type,election_year,region_code,party_code,vote_count,data_status
legislative_dpr,2024,00.01.01,UJI_A,120,official
legislative_dpr,2024,00.01.01,UJI_C,0,official
```

## 2. Suara pasangan calon (Pilpres)

| Kolom | Isi |
| --- | --- |
| `election_type` | Selalu `presidential` |
| `election_year` | `2019` atau `2024` |
| `region_code` | Kode Kemendagri |
| `pair_number` | Nomor urut paslon dari `data/reference/candidate_pairs.csv` |
| `vote_count` | Suara paslon |
| `data_status` | `official`, dst. |

## 3. Partisipasi

| Kolom | Isi |
| --- | --- |
| `election_type`, `election_year`, `region_code`, `data_status` | Seperti di atas |
| `registered_voters` | DPT. Boleh kosong bila tidak tersedia |
| `voters_turned_out` | Pengguna hak pilih. Boleh kosong |
| `valid_votes` | Suara sah. Boleh kosong |
| `invalid_votes` | Suara tidak sah. Boleh kosong |

Minimal satu angka harus terisi. Partisipasi dicatat per kontestasi, karena
suara sah Pilpres, DPR RI, dan DPRD Provinsi berbeda.

Bila suara sah + tidak sah ≠ pengguna hak pilih, atau pengguna hak pilih
melebihi DPT, validator hanya memberi **peringatan**: rekapitulasi resmi kadang
memang begitu (DPTb, DPK). Selisihnya dilaporkan oleh rekonsiliasi (T3.3), tidak
diperbaiki diam-diam.

## Yang tidak diperiksa validator

- Kecocokan total dengan rekapitulasi resmi: T3.3.
- Kelengkapan wilayah dan partai: T3.5.

## Menjalankan

Database harus sudah berisi data referensi (`make seed`) dan wilayah (T2.2).
Validator hanya membaca; tidak ada yang ditulis.

```
make validate f=path/ke/berkas.csv
```

Windows: `.\make.ps1 validate path\ke\berkas.csv`.

Kode keluar 0 bila lolos, 1 bila gagal. Semua kesalahan dilaporkan sekaligus
dengan nama berkas dan nomor barisnya; checksum SHA-256 berkas ikut dicetak
untuk dicatat di versi dataset.
