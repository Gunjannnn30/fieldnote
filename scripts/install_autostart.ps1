<#
.SYNOPSIS
  Register Fieldnote to start automatically at logon.

.DESCRIPTION
  Creates a scheduled task that runs scripts\publish.ps1 every time the user
  logs on. The service and the public tunnel therefore come back on their own
  after a restart or a reboot, and the current public URL is always in
  data\artifacts\live_url.txt.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1
#>
[CmdletBinding()]
param(
  [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$script = Join-Path $root 'scripts\publish.ps1'
$taskName = 'Fieldnote'

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "removed the scheduled task '$taskName'"
    exit 0
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description 'Fieldnote service and public tunnel' -Force | Out-Null

Write-Host "installed the scheduled task '$taskName' - it runs at every logon"
Write-Host "start it now with:  Start-ScheduledTask -TaskName $taskName"
Write-Host "remove it with:     scripts\install_autostart.ps1 -Remove"
