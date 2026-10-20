<#
.SYNOPSIS
  Bring up Fieldnote in Docker and publish it.

.DESCRIPTION
  Builds the image, starts the service, waits for it to become healthy, then
  opens a public https tunnel and prints the URL.

.EXAMPLE
  ./scripts/docker_up.ps1
#>
[CmdletBinding()]
param(
  [int]$Port = 8000,
  [switch]$NoTunnel
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw 'docker is not on PATH'
}
docker compose version *> $null
if ($LASTEXITCODE -ne 0) { throw 'docker compose v2 is required' }

Write-Host '==> building the image (models are baked in, so this takes a while)' -ForegroundColor Cyan
docker compose build
if ($LASTEXITCODE -ne 0) { throw 'build failed' }

Write-Host '==> starting the service' -ForegroundColor Cyan
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw 'compose up failed' }

Write-Host '==> waiting for it to become healthy (the first start builds the corpus)' -ForegroundColor Cyan
$healthy = $false
for ($i = 0; $i -lt 120; $i++) {
    $state = docker inspect -f '{{.State.Health.Status}}' fieldnote 2>$null
    if ($state -eq 'healthy') { Write-Host '    healthy' -ForegroundColor Green; $healthy = $true; break }
    if ($state -eq 'unhealthy') { docker compose logs --tail 40; throw 'container reported unhealthy' }
    Start-Sleep -Seconds 5
}
if (-not $healthy) { docker compose logs --tail 40; throw 'timed out waiting for health' }

Write-Host ''
Write-Host "    local     http://localhost:$Port/"
Write-Host "    api docs  http://localhost:$Port/docs"

if (-not $NoTunnel -and (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host ''
    Write-Host '==> opening a public tunnel' -ForegroundColor Cyan
    $log = Join-Path $env:TEMP 'fieldnote-tunnel.log'
    $proc = Start-Process -FilePath 'cloudflared' `
        -ArgumentList @('tunnel', '--url', "http://127.0.0.1:$Port", '--no-autoupdate') `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" -NoNewWindow -PassThru
    for ($i = 0; $i -lt 60; $i++) {
        $url = (Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue |
                Select-Object -First 1).Matches.Value
        if ($url) {
            Write-Host ''
            Write-Host "    LIVE UI   $url/" -ForegroundColor Green
            Write-Host "    LIVE API  $url/docs" -ForegroundColor Green
            break
        }
        Start-Sleep -Seconds 1
    }
    Write-Host '    (the tunnel closes when this window is closed)'
    $proc | Wait-Process
}
else {
    Write-Host ''
    Write-Host 'cloudflared not found or -NoTunnel given - the service is on localhost only.'
    docker compose logs -f
}
