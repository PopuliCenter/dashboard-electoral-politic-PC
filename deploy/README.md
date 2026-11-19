# deploy

Berkas operasi produksi. Rinciannya dikerjakan di Tahap 6.

| Berkas | Isi | Tugas |
| --- | --- | --- |
| `docker-compose.prod.yml` | Server A (publik, hanya 443) dan Server B (hanya lewat VPN) | T6.1 |
| `nginx/` | Terminasi TLS, cache tiles, header keamanan | T6.1, T6.4 |
| `scripts/backup.sh` | `pg_dump` terenkripsi, tiap malam dan setelah tiap impor, retensi 7 hari | T6.2 |
| `scripts/restore-test.sh` | Pulihkan dump terbaru ke staging, bandingkan jumlah baris dan total suara | T6.3 |

Aturan rute backup (lihat `docs/REVISI-v1.1.md` bagian 6): **NAS yang menarik, bukan VPS yang mendorong.**
Server tidak pernah menyimpan kredensial NAS. Backup yang belum pernah dipulihkan dianggap belum ada.
