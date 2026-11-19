# Catatan Keputusan

Satu baris per keputusan. Keputusan gerbang (Gerbang 1, 2, 3 di `TASKS.md`) wajib dicatat di sini.

| Tanggal | Topik | Keputusan | Alasan | Oleh |
| --- | --- | --- | --- | --- |
| 2026-11-19 | Tahap 0 — basis image | Backend Python 3.12-slim, bukan 3.14 | Roda biner untuk asyncpg dan dependensi lain paling matang di 3.12 | Tim |
| 2026-11-19 | Tahap 0 — Alembic | `env.py` memakai engine async dan membaca `DATABASE_URL` dari environment | Satu driver (asyncpg) saja; URL database tidak pernah masuk `alembic.ini` | Tim |
| 2026-11-19 | Tahap 0 — perintah | `make check` menjalankan lint dan test di dalam kontainer, bukan di host | Hasil sama di laptop mana pun; tidak butuh Python atau Node terpasang. Windows memakai `make.ps1` | Tim |

## Keputusan terbuka (dari `REVISI-v1.1.md` bagian 10)

Jangan diasumsikan di dalam kode sampai diputuskan.

- [ ] Dua server KVM 2, atau satu server ditambah NAS.
- [ ] Jumlah orang dan jam kerja per minggu.
- [ ] Persentase kecamatan Jawa Barat yang punya rekapitulasi resmi 2019 dan 2024 (**Gerbang 1**).
- [ ] Bolehkah data Sirekap/Situng ditampilkan dengan label tidak resmi.
- [ ] Lokasi, kecepatan unggah, dan pengelola NAS.
- [ ] Ambang n minimum agar agregat survei boleh tampil per wilayah (fase 2).
