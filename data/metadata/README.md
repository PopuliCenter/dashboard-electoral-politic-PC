# data/metadata

Inventaris sumber, kamus data, dan template untuk data yang dipakai dashboard.
Semuanya berkas kecil tanpa data individu, jadi boleh masuk Git. Template hanya
berisi baris judul: tidak ada angka contoh yang bisa ikut termuat.

| Berkas | Isi |
| --- | --- |
| `source_inventory.csv` | Satu baris per sumber atau dokumen: fase v1.1, prioritas, URL halaman dan berkas, format, tingkat wilayah, status resmi, ketersediaan, dan lokasi salinan mentah. Ringkasannya di `docs/data-inventory.md` |
| `data_dictionary.csv` | Arti, tipe, dan nilai yang diizinkan untuk setiap kolom di template, `source_inventory.csv`, `data/reference/kode_wilayah_jabar.csv`, dan `data/raw/MANIFEST.csv` |
| `templates/impor_suara_partai.csv` | Format impor baku suara partai (T3.1). Aturannya di `docs/format-impor.md` |
| `templates/impor_suara_paslon.csv` | Format impor baku suara pasangan calon |
| `templates/impor_partisipasi.csv` | Format impor baku DPT, pengguna hak pilih, suara sah dan tidak sah |
| `templates/padanan_wilayah.csv` | Padanan kode wilayah 2019 → 2024 (T2.3) |
| `templates/dapil.csv`, `dapil_wilayah.csv`, `dapil_peserta.csv` | Dapil, wilayah cakupannya, dan partai yang punya calon per dapil (T2.6) |
| `templates/rekonsiliasi.csv` | Lembar pembanding: angka resmi lawan angka yang dibandingkan, per kab/kota (T3.3, Gerbang 2) |
| `templates/demografi_bps.csv`, `survei_agregat.csv`, `media_agregat.csv` | Fase 2 (REVISI-v1.1 bagian 3 dan 7); belum dipakai |

## Memperbarui inventaris

Setiap sumber baru dicatat dulu di `source_inventory.csv` dengan URL yang sudah
dicek, baru diambil. Dokumen dengan `auto_fetch=ya` diunduh oleh:

```
python pipeline/extract/kpu_dokumen.py fetch      # unduh yang belum ada ke data/raw/
python pipeline/extract/kpu_dokumen.py manifest   # catat checksum di data/raw/MANIFEST.csv
```

Sumber lain punya skripnya sendiri di `pipeline/extract/` (batas wilayah BIG,
salinan Sirekap). Dokumen di Google Drive, hasil permohonan PPID, atau berkas
yang diserahkan langsung diarsipkan dengan:

```
python pipeline/extract/arsip_lokal.py BERKAS... --dest data/raw/<sumber>/<tahun> \
    --source "Penerbit: nama dokumen" --origin "URL asal, atau keterangan bila tidak ada" \
    [--election-year 2024] [--election-type legislative_dpr] [--region-level district] [--notes "..."]
```

Berkas disalin apa adanya dan dicatat di MANIFEST; lalu tambahkan barisnya di
`source_inventory.csv`.
