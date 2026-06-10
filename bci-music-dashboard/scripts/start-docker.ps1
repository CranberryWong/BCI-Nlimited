$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

New-Item -ItemType Directory -Force "models" | Out-Null
New-Item -ItemType Directory -Force "backend/data/presets" | Out-Null
New-Item -ItemType Directory -Force "backend/data/sessions" | Out-Null
New-Item -ItemType Directory -Force "xdf-records" | Out-Null

docker compose up -d --build
docker compose ps

Write-Host ""
Write-Host "Dashboard: http://127.0.0.1:5173"
Write-Host "API docs: http://127.0.0.1:8001/docs"
