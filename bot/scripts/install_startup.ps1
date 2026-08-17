# Install current-user Startup + HKCU Run so a laptop shutdown/reboot brings Aegis back.
# No admin. Does not flatten. Does not mt5.shutdown.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$KeepAlive = Join-Path $ScriptDir "supervisor_keepalive.ps1"
$Cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$KeepAlive`" -Loop -IntervalSeconds 1200"

$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
New-Item -ItemType Directory -Force -Path $startupDir | Out-Null
$bat = Join-Path $startupDir "AegisKeepAlive.cmd"
@(
    "@echo off"
    "start `"`" /MIN $Cmd"
) | Set-Content -Path $bat -Encoding ascii

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
New-Item -Path $runKey -Force | Out-Null
Set-ItemProperty -Path $runKey -Name "AegisKeepAlive" -Value $Cmd

Write-Host "Installed logon autostart:"
Write-Host "  $bat"
Write-Host "  HKCU Run\AegisKeepAlive"
Write-Host "After a shutdown, Windows logon starts MT5 (if needed), the paper runner, and the optimizer."
Write-Host "Daily-loss halt in bot/reports/risk_state.json is kept. Positions are not flattened."
