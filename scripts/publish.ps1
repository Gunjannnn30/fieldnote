<#
.SYNOPSIS
  Run Fieldnote as a durable published service with a public URL.

.DESCRIPTION
  Starts the API, waits for it to be healthy, opens a cloudflared tunnel, and
  writes the public URL to data\artifacts\live_url.txt.

  Unlike `fieldnote serve --tunnel`, this script detaches: it keeps running
  after the shell that started it is closed, and it restarts the server or the
  tunnel if either of them dies.

  Pass -Docker to serve the Docker Compose stack instead of the local
  process (the container is preferred once Docker's engine is available).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\publish.ps1
#>
[CmdletBinding()]
param(
  [int]$Port = 8000,
  [switch]$Docker,
  [string]$ApiKey = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

if ($ApiKey) { $env:FIELDNOTE_API_KEY = $ApiKey }
else { Remove-Item Env:\FIELDNOTE_API_KEY -ErrorAction SilentlyContinue }

$artifacts = Join-Path $root 'data\artifacts'
New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
$urlFile = Join-Path $artifacts 'live_url.txt'
$serverLog = Join-Path $artifacts 'server.log'
$tunnelLog = Join-Path $artifacts 'tunnel.log'

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Get-LiveUrl {
    if (Test-Path $urlFile) { return (Get-Content $urlFile -Raw).Trim() }
    return $null
}

function Test-Healthy {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 5
        return $r.status -eq 'ok'
    } catch { return $false }
}

# ---------------------------------------------------------------- server
$server = $null
if ($Docker) {
    Write-Step 'starting the Docker Compose stack'
    docker compose up -d
} else {
    Write-Step 'starting the API'
    $python = (Get-Command python).Source
    $server = Start-Process -FilePath $python `
        -ArgumentList @('-m', 'uvicorn', 'fieldnote.serve.app:app',
                        '--host', '127.0.0.1', '--port', "$Port", '--log-level', 'warning') `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput $serverLog -RedirectStandardError "$serverLog.err" -PassThru
}

Write-Step 'waiting for it to become healthy'
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    if (Test-Healthy) { $ok = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ok) { throw "the service did not become healthy on port $Port" }
Write-Host '    healthy' -ForegroundColor Green

# ---------------------------------------------------------------- tunnel
function Start-Tunnel {
    Write-Step 'opening a public tunnel'
    if (Test-Path $tunnelLog) { Remove-Item $tunnelLog -Force -ErrorAction SilentlyContinue }
    $cf = (Get-Command cloudflared -ErrorAction SilentlyContinue)
    if (-not $cf) { throw 'cloudflared is not on PATH' }
    $p = Start-Process -FilePath $cf.Source `
        -ArgumentList @('tunnel', '--url', "http://127.0.0.1:$Port", '--no-autoupdate') `
        -WindowStyle Hidden -RedirectStandardOutput $tunnelLog -RedirectStandardError "$tunnelLog.err" -PassThru
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 1
        # cloudflared prints its banner on stderr, so look in both.
        $url = $null
        foreach ($f in @($tunnelLog, "$tunnelLog.err")) {
            if (Test-Path $f) {
                $m = Select-String -Path $f -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' |
                     Select-Object -First 1
                if ($m) { $url = $m.Matches.Value; break }
            }
        }
        if ($url) {
            Set-Content -Path $urlFile -Value $url -Encoding UTF8
            Write-Host ''
            Write-Host "    LIVE UI   $url/" -ForegroundColor Green
            Write-Host "    LIVE API  $url/docs" -ForegroundColor Green
            if ($ApiKey) {
                Write-Host "    API key   $ApiKey  (send it as X-Fieldnote-Key, or ?key=)" -ForegroundColor DarkGray
            }
            Write-Host "    url file  $urlFile" -ForegroundColor DarkGray
            Write-Host ''
            Publish-StableUrl -LiveUrl $url
            return $p
        }
        if ($p.HasExited) { throw 'cloudflared exited before publishing a url' }
    }
    throw 'cloudflared did not publish a url in time'
}

function Publish-StableUrl {
    <#
      A quick tunnel gets a random address, so the address in the url file
      changes whenever the tunnel restarts. The stable address - a GitHub
      Pages redirect that reads the current address from a gist - is written
      to stable_url.txt so there is always one link worth sharing.
    #>
    param([Parameter(Mandatory = $true)][string]$LiveUrl)

    $script = Join-Path $root 'scripts\publish_url.py'
    if (-not (Test-Path $script)) { return }
    try {
        $out = (& python $script $LiveUrl 2>&1 | Out-String)
        $out | Out-File -FilePath (Join-Path $artifacts 'publish_url.log') -Encoding UTF8
        $stable = $null
        if ($out -match 'stable\s*:\s*(\S+)') { $stable = $Matches[1] }
        if ($stable) {
            Set-Content -Path (Join-Path $artifacts 'stable_url.txt') -Value $stable -Encoding UTF8
            Write-Host "    STABLE    $stable" -ForegroundColor Green
            Write-Host "    (that address never changes; it always points here)" -ForegroundColor DarkGray
            Write-Host ''
        } else {
            Write-Host "    could not publish the stable address - see publish_url.log" -ForegroundColor DarkYellow
        }    } catch {
        Write-Host "    could not publish the stable address: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }
}

$tunnel = Start-Tunnel

# ---------------------------------------------------------------- watchdog
Write-Step 'watching (the tunnel is restarted automatically if it drops)'
while ($true) {
    Start-Sleep -Seconds 20
    if (-not (Test-Healthy)) {
        Write-Step 'the API is down - restarting it'
        if ($Docker) { docker compose up -d } else {
            $python = (Get-Command python).Source
            $server = Start-Process -FilePath $python `
                -ArgumentList @('-m', 'uvicorn', 'fieldnote.serve.app:app',
                                '--host', '127.0.0.1', '--port', "$Port", '--log-level', 'warning') `
                -WorkingDirectory $root -WindowStyle Hidden `
                -RedirectStandardOutput $serverLog -RedirectStandardError "$serverLog.err" -PassThru
        }
        for ($i = 0; $i -lt 60; $i++) { if (Test-Healthy) { break }; Start-Sleep -Seconds 2 }
        Write-Step 'the API is back'
    }
    if ($tunnel.HasExited) {
        Write-Step 'the tunnel dropped - reopening it'
        $tunnel = Start-Tunnel
    }
}
