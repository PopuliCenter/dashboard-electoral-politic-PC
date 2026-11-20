# Perintah proyek. Semuanya berjalan di dalam kontainer supaya hasilnya sama
# di laptop siapa pun dan di CI. Windows: pakai .\make.ps1 <target>.

COMPOSE := docker compose
RUN_API := $(COMPOSE) run --rm --no-deps api sh -lc
RUN_WEB := $(COMPOSE) run --rm --no-deps web sh -lc

.PHONY: help up down logs build check check-backend check-frontend fmt test migrate revision seed seed-dry validate staging-init load datasets promote completeness users shell-api shell-db reset

help:
	@echo "up              jalankan db, api, web"
	@echo "down            hentikan kontainer"
	@echo "logs            ikuti log semua layanan"
	@echo "build           bangun ulang image"
	@echo "check           lint + type check + test (backend dan frontend)"
	@echo "fmt             format ulang kode"
	@echo "test            pytest backend saja"
	@echo "migrate         alembic upgrade head"
	@echo "revision m=...  buat migrasi baru (autogenerate)"
	@echo "seed            isi kontestasi, paslon, partai dari data/reference"
	@echo "seed-dry        validasi dan tampilkan perubahan seed tanpa menulis"
	@echo "validate f=...  validasi berkas impor baku (CSV), tanpa menulis"
	@echo "staging-init    buat database staging lokal, migrasi, dan seed"
	@echo "load f=... a=.. validasi lalu muat berkas ke staging (a: --dataset, --source-name, ...)"
	@echo "datasets        daftar versi dataset di staging dan statusnya"
	@echo "promote v=ID    promosikan satu versi staging ke produksi (a=--dry-run untuk uji)"
	@echo "users a=...     kelola pengguna (a=\"create EMAIL --name NAMA --role admin\", list, ...)"
	@echo "completeness    laporan kelengkapan (a=\"--db staging --detail --format csv\")"

up:
	$(COMPOSE) up -d
	@echo "web http://localhost:3000   api http://localhost:8000/docs"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

build:
	$(COMPOSE) build

check: check-backend check-frontend

check-backend:
	@echo "== backend: ruff, mypy, pytest =="
	$(RUN_API) "ruff check . && ruff format --check . && mypy && pytest -m 'not integration' -q"

check-frontend:
	@echo "== frontend: eslint, tsc, prettier =="
	$(RUN_WEB) "npm run lint && npm run typecheck && npm run format:check"

fmt:
	$(RUN_API) "ruff format . && ruff check --fix ."
	$(RUN_WEB) "npm run format"

test:
	$(RUN_API) "pytest -q"

migrate:
	$(COMPOSE) run --rm api alembic upgrade head

seed:
	$(COMPOSE) run --rm api python -m app.seed

seed-dry:
	$(COMPOSE) run --rm api python -m app.seed --dry-run

# Berkas di-mount read-only ke /import; nama berkas dipertahankan supaya pesan
# galat menyebut nama yang sama dengan yang dibuka peneliti. realpath/basename
# di shell, bukan $(abspath)/$(notdir): fungsi make memecah path berspasi.
validate:
	@test -n "$(f)" || (echo "pakai: make validate f=path/ke/berkas.csv" && exit 1)
	@src="$$(realpath "$(f)")" && name="$$(basename "$$src")" && \
		$(COMPOSE) run --rm -v "$$src:/import/$$name:ro" api python -m app.importer "/import/$$name"

# Lokal, staging adalah database kedua di kontainer db yang sama. Migrasi dan
# seed dijalankan dengan DATABASE_URL diarahkan ke STAGING_DATABASE_URL.
STAGING_DB ?= populi_staging
staging-init:
	$(COMPOSE) exec -T db sh -c 'psql -U "$$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '\''$(STAGING_DB)'\''" | grep -q 1 || createdb -U "$$POSTGRES_USER" $(STAGING_DB)'
	$(COMPOSE) run --rm api sh -lc 'DATABASE_URL="$$STAGING_DATABASE_URL" alembic upgrade head && DATABASE_URL="$$STAGING_DATABASE_URL" python -m app.seed'

load:
	@test -n "$(f)" || (echo "pakai: make load f=berkas.csv a=\"--dataset NAMA --source-name NAMA ...\"" && exit 1)
	@src="$$(realpath "$(f)")" && name="$$(basename "$$src")" && \
		$(COMPOSE) run --rm -v "$$src:/import/$$name:ro" api python -m app.datasets load "/import/$$name" $(a)

datasets:
	$(COMPOSE) run --rm api python -m app.datasets list

promote:
	@test -n "$(v)" || (echo "pakai: make promote v=VERSION_ID [a=--dry-run]" && exit 1)
	$(COMPOSE) run --rm api python -m app.datasets promote $(v) $(a)

# Interaktif: password diminta lewat prompt tersembunyi, tidak lewat argumen.
users:
	$(COMPOSE) run --rm api python -m app.users $(a)

completeness:
	$(COMPOSE) run --rm api python -m app.reports completeness $(a)

revision:
	@test -n "$(m)" || (echo "pakai: make revision m=\"pesan migrasi\"" && exit 1)
	$(COMPOSE) run --rm api alembic revision --autogenerate -m "$(m)"

shell-api:
	$(COMPOSE) exec api bash

shell-db:
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-populi} -d $${POSTGRES_DB:-populi}

# Hapus kontainer DAN volume database lokal. Hanya untuk pengembangan.
reset:
	$(COMPOSE) down -v
