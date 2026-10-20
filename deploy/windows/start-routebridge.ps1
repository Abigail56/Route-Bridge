# Starts RouteBridge on this computer, for example after a restart. Safe to run at any time: it never rebuilds
# anything and never touches your data. Right-click > "Run with PowerShell", or:  powershell -ExecutionPolicy Bypass -File deploy\windows\start-routebridge.ps1

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Docker-Ready {
    try { docker info --format '{{.ServerVersion}}' 2>$null | Out-Null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}
function Code($url) {
    try { return [int](Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 20).StatusCode } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode } else { return 0 }
    }
}

Step '1/4  Docker Desktop'
if (-not (Docker-Ready)) {
    $exe = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'
    if (-not (Test-Path $exe)) { $exe = 'C:\Program Files\Docker\Docker\Docker Desktop.exe' }
    if (-not (Test-Path $exe)) { Write-Host 'Docker Desktop was not found. Install it first.' -ForegroundColor Red; exit 1 }
    Write-Host 'Starting Docker Desktop (this can take a few minutes)...'
    Start-Process $exe
    $waited = 0
    while (-not (Docker-Ready) -and $waited -lt 600) { Start-Sleep -Seconds 10; $waited += 10; Write-Host "  waiting for Docker... $waited s" }
    if (-not (Docker-Ready)) {
        Write-Host 'Docker did not start within 10 minutes.' -ForegroundColor Red
        Write-Host 'Quit Docker Desktop, run:  wsl --shutdown   then open Docker Desktop again and re-run this script.'
        exit 1
    }
}
Write-Host 'Docker is running.' -ForegroundColor Green

Step '2/4  Starting RouteBridge (nothing is rebuilt)'
$env:COMPOSE_IGNORE_ORPHANS = 'true'   # an old leftover container from an earlier version is harmless; do not warn about it
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --no-build postgres redis minio api outbox-worker notification-worker maintenance-worker web web-demo
if ($LASTEXITCODE -ne 0) { Write-Host 'Something did not start. Run deploy\windows\health-check.ps1 to see what.' -ForegroundColor Red; exit 1 }

Step '3/4  Waiting until it answers'
$ok = $false
for ($i = 0; $i -lt 18; $i++) {
    $api = Code 'http://localhost:8000/health'; $pc = Code 'http://localhost:3000/sign-in'; $phone = Code 'http://localhost:3100/sign-in'
    Write-Host "  api=$api  pc-site=$pc  phone-site=$phone"
    if ($api -eq 200 -and $pc -eq 200 -and $phone -eq 200) { $ok = $true; break }
    Start-Sleep -Seconds 10
}
if ($ok) { Write-Host 'RouteBridge is up.' -ForegroundColor Green } else { Write-Host 'Not everything answered yet. Run deploy\windows\health-check.ps1 in a minute.' -ForegroundColor Yellow }

Step '4/4  The public phone link'
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $ts) { $candidate = 'C:\Program Files\Tailscale\tailscale.exe'; if (Test-Path $candidate) { $ts = $candidate } }
if ($ts) {
    $status = (& $ts funnel status 2>&1 | Out-String)
    if ($status -match '3100') { Write-Host 'Tailscale Funnel is serving the phone site.' -ForegroundColor Green }
    else { Write-Host 'The phone link is not published. To publish it, run:  tailscale funnel --bg 3100' -ForegroundColor Yellow }
} else { Write-Host 'Tailscale was not found, so the phone link cannot be checked.' -ForegroundColor Yellow }

Write-Host ""
Write-Host 'PC:     http://localhost:3000'
Write-Host 'Phone:  https://neche.taile59d7a.ts.net'
Write-Host ""
Write-Host 'Tip: set Windows to never sleep while plugged in, or the phone link goes down.'
