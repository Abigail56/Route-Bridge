# Read-only health check: is everything running, is the database healthy, is there room, and is there a recent backup?
# powershell -ExecutionPolicy Bypass -File deploy\windows\health-check.ps1

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $root

function Code($url) {
    try { return [int](Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 25).StatusCode } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode } else { return 0 }
    }
}
function Show($name, $good, $detail) {
    $mark = if ($good) { '[ OK ]' } else { '[FAIL]' }
    $color = if ($good) { 'Green' } else { 'Red' }
    Write-Host ("{0} {1,-34} {2}" -f $mark, $name, $detail) -ForegroundColor $color
}

Write-Host "RouteBridge health check  ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))" -ForegroundColor Cyan
Write-Host ""

$engine = $false
try { docker info --format '{{.ServerVersion}}' 2>$null | Out-Null; $engine = ($LASTEXITCODE -eq 0) } catch { }
Show 'Docker engine' $engine $(if ($engine) { 'running' } else { 'NOT running: run deploy\windows\start-routebridge.ps1' })

$a = Code 'http://localhost:8000/health';       Show 'API (localhost:8000)' ($a -eq 200) "HTTP $a"
$w = Code 'http://localhost:3000/sign-in';      Show 'PC site (localhost:3000)' ($w -eq 200) "HTTP $w"
$d = Code 'http://localhost:3100/sign-in';      Show 'Phone site, local (3100)' ($d -eq 200) "HTTP $d"
$p = Code 'https://neche.taile59d7a.ts.net/sign-in'; Show 'Phone link (public)' ($p -eq 200) "HTTP $p"

if ($engine) {
    Write-Host ""
    Write-Host 'Containers' -ForegroundColor Cyan
    $wanted = 'postgres','redis','minio','api','outbox-worker','notification-worker','maintenance-worker','web','web-demo'
    $running = docker ps --format '{{.Names}}|{{.Status}}'
    foreach ($svc in $wanted) {
        $line = $running | Where-Object { $_ -match "routebridge-$svc-1\|" -or $_ -match "-routebridge-$svc-1\|" } | Select-Object -First 1
        if ($line) { $status = ($line -split '\|')[1]; Show $svc ($status -notmatch 'unhealthy|Restarting') $status } else { Show $svc $false 'not running' }
    }
    Write-Host ""
    Write-Host 'Database' -ForegroundColor Cyan
    $version = (docker exec routebridge-postgres-1 psql -U routebridge -d routebridge -t -A -c 'select version_num from alembic_version' 2>$null | Out-String).Trim()
    $tenants = (docker exec routebridge-postgres-1 psql -U routebridge -d routebridge -t -A -c 'select count(*) from tenant' 2>$null | Out-String).Trim()
    Show 'Migration version' ($version.Length -gt 0) $version
    Show 'Workspaces' ($tenants.Length -gt 0) $tenants
}

Write-Host ""
Write-Host 'This computer' -ForegroundColor Cyan
$os = Get-CimInstance Win32_OperatingSystem
$freeMb = [int]($os.FreePhysicalMemory / 1024)
Show 'Free memory' ($freeMb -gt 400) "$freeMb MB  (builds need about 1000 MB free)"
$drive = Get-PSDrive -Name C
$freeGb = [math]::Round($drive.Free / 1GB, 1)
Show 'Free disk space (C:)' ($freeGb -gt 10) "$freeGb GB"

$folder = Join-Path $env:USERPROFILE 'RouteBridgeBackups'
$latest = if (Test-Path $folder) { Get-ChildItem $folder -Filter '*.dump' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 } else { $null }
if ($latest) {
    $age = [math]::Round(((Get-Date) - $latest.LastWriteTime).TotalHours, 1)
    Show 'Latest backup' ($age -lt 48) "$($latest.Name), $age hours old"
} else { Show 'Latest backup' $false 'none yet: run deploy\windows\backup-now.ps1' }
