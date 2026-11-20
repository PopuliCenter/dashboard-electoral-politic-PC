# pipeline

Jalur data: dokumen mentah → format impor baku → staging → produksi.
Tidak ada jalur tulis langsung ke database produksi.

| Folder | Isi | Tugas |
| --- | --- | --- |
| `extract/` | Pembaca PDF dan Excel KPU (Camelot, Pandas) → CSV format baku | T3.2 |
| `validate/` | Skrip rekonsiliasi total per kab/kota. Validator format impor (T3.1) ada di `backend/app/importer/` supaya dipakai juga oleh antarmuka unggah T5.2; formatnya di `docs/format-impor.md` | T3.1, T3.3 |
| `load/` | Muat ke staging, promosi staging → produksi, tulis `dataset_versions` dan `audit_logs` | T3.4 |
| `tiles/` | Batas wilayah → tippecanoe → PMTiles di `data/tiles/` | T2.4 |

Aturan yang berlaku di seluruh folder ini:

1. Dokumen di `data/raw/` tidak pernah diubah. Koreksi menjadi versi dataset baru.
2. Angka yang tidak terbaca ditandai tidak tersedia, tidak pernah ditebak.
3. Hasil ekstraksi selalu masuk staging dulu; yang gagal validasi tidak boleh menggantikan data produksi.
