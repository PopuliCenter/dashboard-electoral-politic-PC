# Perintah proyek. Semuanya berjalan di dalam kontainer supaya hasilnya sama
# di laptop siapa pun dan di CI. Windows: pakai .\make.ps1 <target>.

COMPOSE := docker compose
RUN_API := $(COMPOSE) run --rm --no-deps api sh -lc
RUN_WEB := $(COMPOSE) run --rm --no-deps web sh -lc

.PHONY: help up down logs build check check-backend check-frontend fmt test migrate revision seed seed-dry validate shell-api shell-db reset

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
# galat menyebut nama yang sama dengan yang dibuka peneliti.
validate:
	@test -n "$(f)" || (echo "pakai: make validate f=path/ke/berkas.csv" && exit 1)
	$(COMPOSE) run --rm -v "$(abspath $(f)):/import/$(notdir $(f)):ro" api python -m app.importer "/import/$(notdir $(f))"

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
