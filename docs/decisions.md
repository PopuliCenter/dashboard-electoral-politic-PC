# Catatan Keputusan

Satu baris per keputusan. Keputusan gerbang (Gerbang 1, 2, 3 di `TASKS.md`) wajib dicatat di sini.

| Tanggal | Topik | Keputusan | Alasan | Oleh |
| --- | --- | --- | --- | --- |
| 2026-11-19 | Tahap 0 — basis image | Backend Python 3.12-slim, bukan 3.14 | Roda biner untuk asyncpg dan dependensi lain paling matang di 3.12 | Tim |
| 2026-11-19 | Tahap 0 — Alembic | `env.py` memakai engine async dan membaca `DATABASE_URL` dari environment | Satu driver (asyncpg) saja; URL database tidak pernah masuk `alembic.ini` | Tim |
| 2026-11-19 | Tahap 0 — perintah | `make check` menjalankan lint dan test di dalam kontainer, bukan di host | Hasil sama di laptop mana pun; tidak butuh Python atau Node terpasang. Windows memakai `make.ps1` | Tim |
| 2026-11-20 | T2.1 — pasangan calon | Tabel `candidate_pairs` hanya menyimpan nomor urut dan nama paslon | `candidate_results` butuh identitas paslon, sedangkan profil kandidat ditunda ke fase 2+ | Tim |
| 2026-11-20 | T2.1 — vote share | `vote_share` dan `swing` tidak punya kolom di tabel mana pun | Keduanya dihitung dari `vote_count` dan suara sah; menyimpannya membuat dua sumber kebenaran | Tim |
| 2026-11-20 | T2.1 — partisipasi | Hubungan antar angka partisipasi (sah + tidak sah = pengguna hak pilih) tidak dipasang sebagai CHECK | CHECK akan menolak rekapitulasi resmi yang ganjil; selisih dilaporkan oleh rekonsiliasi T3.3, bukan disembunyikan | Tim |
| 2026-11-20 | T2.1 — Pilpres di `candidate_results` | Bahwa `election_id` menunjuk kontestasi Pilpres ditegakkan validator impor, bukan CHECK | Jenis kontestasi ada di tabel lain; CHECK lintas tabel butuh trigger yang tidak sepadan di fase 1 | Tim |
| 2026-11-20 | T2.1 — Alembic dan PostGIS | Autogenerate dibatasi ke skema `public` dan hanya melihat tabel yang didefinisikan di `app/models` | Ekstensi PostGIS (topology, tiger geocoder) membuat puluhan tabel; tanpa batas ini Alembic mengusulkan men-drop semuanya | Tim |
| 2026-11-20 | T2.1 — commit migrasi | `env.py` memanggil `connection.commit()` eksplisit setelah `run_sync` | `SET search_path` membuka transaksi implisit sehingga transaksi Alembic menjadi no-op; tanpa commit, DDL ter-rollback diam-diam sementara alembic tetap melaporkan sukses | Tim |
| 2026-11-20 | T2.1 — downgrade | Tipe ENUM dibuang eksplisit di `downgrade()` | PostgreSQL tidak ikut menghapus tipe ENUM saat tabelnya di-drop, sehingga `upgrade head` berikutnya gagal | Tim |

## Keputusan terbuka (dari `REVISI-v1.1.md` bagian 10)

Jangan diasumsikan di dalam kode sampai diputuskan.

- [ ] Dua server KVM 2, atau satu server ditambah NAS.
- [ ] Jumlah orang dan jam kerja per minggu.
- [ ] Persentase kecamatan Jawa Barat yang punya rekapitulasi resmi 2019 dan 2024 (**Gerbang 1**).
- [ ] Bolehkah data Sirekap/Situng ditampilkan dengan label tidak resmi.
- [ ] Lokasi, kecepatan unggah, dan pengelola NAS.
- [ ] Ambang n minimum agar agregat survei boleh tampil per wilayah (fase 2).
