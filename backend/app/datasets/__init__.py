"""Muat ke staging dan promosi staging -> produksi (T3.4).

Alur: berkas impor baku -> validasi (app.importer) -> `load` ke database
staging -> `promote` ke database produksi. Tidak ada jalur yang menulis hasil
pemilu langsung ke produksi (aturan data 6).
"""
