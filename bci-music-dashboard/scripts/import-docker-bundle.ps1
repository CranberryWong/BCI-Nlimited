param(
    [string]$ImageArchive = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not $ImageArchive) {
    $ImageArchive = Get-ChildItem -Path $Root -Filter "bci-music-dashboard-images-*.tar.gz" |
        Select-Object -First 1 -ExpandProperty FullName
}

if (-not $ImageArchive) {
    throw "Docker image archive was not found."
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

New-Item -ItemType Directory -Force "models" | Out-Null
New-Item -ItemType Directory -Force "backend/data/presets" | Out-Null
New-Item -ItemType Directory -Force "backend/data/sessions" | Out-Null
New-Item -ItemType Directory -Force "xdf-records" | Out-Null

Write-Host "Loading Docker images..."
docker load -i $ImageArchive

Write-Host "Starting BCI Music Dashboard..."
docker compose up -d --no-build

Write-Host ""
Write-Host "Dashboard: http://127.0.0.1:5173"
Write-Host "API docs: http://127.0.0.1:8001/docs"
Write-Host "Check status with: docker compose ps"
