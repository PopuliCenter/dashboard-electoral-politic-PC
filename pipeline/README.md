# pipeline

Jalur data: dokumen mentah → format impor baku → staging → produksi.
Tidak ada jalur tulis langsung ke database produksi.

| Folder | Isi | Tugas |
| --- | --- | --- |
| `extract/` | Pembaca PDF dan Excel KPU (Camelot, Pandas) → CSV format baku | T3.2 |
| `validate/` | Skrip rekonsiliasi total per kab/kota. Validator format impor (T3.1) ada di `backend/app/importer/` supaya dipakai juga oleh antarmuka unggah T5.2; formatnya di `docs/format-impor.md` | T3.1, T3.3 |
| `load/` | Muat ke staging, promosi staging → produksi, tulis `dataset_versions` dan `audit_logs`. Implementasinya di `backend/app/datasets/` (lihat di bawah) | T3.4 |
| `tiles/` | Batas wilayah → tippecanoe → PMTiles di `data/tiles/` | T2.4 |

Aturan yang berlaku di seluruh folder ini:

1. Dokumen di `data/raw/` tidak pernah diubah. Koreksi menjadi versi dataset baru.
2. Angka yang tidak terbaca ditandai tidak tersedia, tidak pernah ditebak.
3. Hasil ekstraksi selalu masuk staging dulu; yang gagal validasi tidak boleh menggantikan data produksi.

## Muat dan promosi (T3.4)

Staging adalah database terpisah dengan skema yang sama (`STAGING_DATABASE_URL`).
Lokal ia database kedua di kontainer `db`; di produksi letaknya di Server B.

```
make staging-init                                   # sekali: buat, migrasi, seed staging
make load f=dpr2024.csv a="--dataset kpu-dpr-2024-kecamatan --source-name 'Rekap DPR 2024 Jabar' --source-type kpu_rekapitulasi --retrieved-at 2026-12-01"
make datasets                                       # daftar versi di staging dan statusnya
make promote v=<version_id> a=--dry-run             # periksa dulu
make promote v=<version_id>                         # tulis ke produksi
```

Windows: `.\make.ps1 staging-init`, `.\make.ps1 load dpr2024.csv --dataset ... --source-name ...`,
`.\make.ps1 datasets`, `.\make.ps1 promote <version_id> --dry-run`.

Aturannya:

- Berkas divalidasi (T3.1) sebelum dimuat. Yang gagal tidak menjadi versi dataset;
  percobaannya tercatat di `ingestion_jobs` dan `audit_logs`.
- Satu `--dataset` selalu berisi satu jenis data dan satu kontestasi. Memuat ulang
  dataset yang sama menghasilkan versi berikutnya yang **menggantikan** baris versi
  sebelumnya, di staging maupun saat dipromosikan ke produksi.
- Satu sel (kontestasi × wilayah × partai/paslon) hanya boleh punya satu angka. Bila
  dataset lain sudah mengisinya, muat atau promosi ditolak; manusia yang memutuskan.
- Promosi memetakan partai, paslon, kontestasi, dan wilayah lewat kode, bukan UUID.
  Data referensi dan wilayah harus sudah ada di produksi lebih dulu.
- Versi yang lebih lama tidak bisa menimpa versi yang lebih baru di produksi.
