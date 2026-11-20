# Shim PowerShell untuk Makefile: Windows tidak punya `make` bawaan.
# Pakai: .\make.ps1 check
param(
    [Parameter(Position = 0)]
    [string]$Target = "help",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Invoke-Step {
    param([string]$Label, [string[]]$Command)
    Write-Host "== $Label ==" -ForegroundColor Cyan
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) {
        throw "$Label gagal (exit $LASTEXITCODE)"
    }
}

$runApi = @("docker", "compose", "run", "--rm", "--no-deps", "api", "sh", "-lc")
$runWeb = @("docker", "compose", "run", "--rm", "--no-deps", "web", "sh", "-lc")

switch ($Target) {
    "help" {
        Write-Host "target: up, down, logs, build, check, fmt, test, migrate, revision, seed, seed-dry, validate, reset"
    }
    "up" {
        Invoke-Step "docker compose up" @("docker", "compose", "up", "-d")
        Write-Host "web http://localhost:3000   api http://localhost:8000/docs"
    }
    "down" { Invoke-Step "docker compose down" @("docker", "compose", "down") }
    "logs" { & docker compose logs -f }
    "build" { Invoke-Step "build" @("docker", "compose", "build") }
    "check" {
        Invoke-Step "backend: ruff, mypy, pytest" ($runApi + "ruff check . && ruff format --check . && mypy && pytest -m 'not integration' -q")
        Invoke-Step "frontend: eslint, tsc, prettier" ($runWeb + "npm run lint && npm run typecheck && npm run format:check")
        Write-Host "check hijau" -ForegroundColor Green
    }
    "fmt" {
        Invoke-Step "backend format" ($runApi + "ruff format . && ruff check --fix .")
        Invoke-Step "frontend format" ($runWeb + "npm run format")
    }
    "test" { Invoke-Step "pytest" ($runApi + "pytest -q") }
    "migrate" { Invoke-Step "alembic upgrade head" @("docker", "compose", "run", "--rm", "api", "alembic", "upgrade", "head") }
    "seed" { Invoke-Step "seed data referensi" @("docker", "compose", "run", "--rm", "api", "python", "-m", "app.seed") }
    "seed-dry" { Invoke-Step "seed (uji, tanpa menulis)" @("docker", "compose", "run", "--rm", "api", "python", "-m", "app.seed", "--dry-run") }
    "validate" {
        if (-not $Rest -or $Rest.Count -eq 0) { throw 'pakai: .\make.ps1 validate berkas.csv' }
        $file = (Resolve-Path $Rest[0]).Path
        $name = Split-Path $file -Leaf
        Invoke-Step "validasi impor" @("docker", "compose", "run", "--rm", "-v", "${file}:/import/${name}:ro", "api", "python", "-m", "app.importer", "/import/$name")
    }
    "revision" {
        if (-not $Rest -or $Rest.Count -eq 0) { throw 'pakai: .\make.ps1 revision "pesan migrasi"' }
        Invoke-Step "alembic revision" @("docker", "compose", "run", "--rm", "api", "alembic", "revision", "--autogenerate", "-m", ($Rest -join " "))
    }
    "reset" { Invoke-Step "down -v" @("docker", "compose", "down", "-v") }
    default { throw "target tidak dikenal: $Target" }
}
