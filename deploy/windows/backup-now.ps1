# Takes a backup of the RouteBridge database, checks that it is real, and keeps the newest 14.
# The backup is saved OUTSIDE the project (in your user folder), because it contains real customer data.
# powershell -ExecutionPolicy Bypass -File deploy\windows\backup-now.ps1

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $root

$folder = Join-Path $env:USERPROFILE 'RouteBridgeBackups'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmm'
$name = "routebridge-$stamp.dump"
$target = Join-Path $folder $name

docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host 'Docker is not running. Run deploy\windows\start-routebridge.ps1 first.' -ForegroundColor Red; exit 1 }

Write-Host 'Backing up the database...'
# dump inside the container, then copy the file out (piping binary data through PowerShell would damage it)
docker exec routebridge-postgres-1 pg_dump -U routebridge -Fc -f /tmp/backup.dump routebridge
if ($LASTEXITCODE -ne 0) { Write-Host 'The dump failed.' -ForegroundColor Red; exit 1 }
# prove it can be read: count the tables with data inside it (done in the container, before the temporary copy is removed)
$check = (docker exec routebridge-postgres-1 sh -c "pg_restore -l /tmp/backup.dump | grep -c 'TABLE DATA'" 2>$null | Out-String).Trim()
docker cp routebridge-postgres-1:/tmp/backup.dump $target
docker exec routebridge-postgres-1 rm -f /tmp/backup.dump | Out-Null

if (-not (Test-Path $target)) { Write-Host 'The backup file was not created.' -ForegroundColor Red; exit 1 }
$size = (Get-Item $target).Length
if ($size -lt 20000) { Write-Host "The backup is only $size bytes: that is not a real backup." -ForegroundColor Red; Remove-Item $target; exit 1 }

if (-not $check) { $check = 'unknown' }
Write-Host ("Saved: {0}  ({1} KB, {2} tables with data)" -f $target, [int]($size / 1024), $check) -ForegroundColor Green

# keep the newest 14
Get-ChildItem $folder -Filter 'routebridge-*.dump' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 14 | Remove-Item -Force
Write-Host "Backups are kept in $folder (newest 14). Copy a recent one to a USB drive or cloud storage now and then."
