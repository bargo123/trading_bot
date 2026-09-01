# Current-user scheduled tasks so the demo survives a closed console / sleep resume.
# Not a privileged Windows service. Paper runner and optimizer are separate processes.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$KeepAlive = Join-Path $ScriptDir "supervisor_keepalive.ps1"
$Tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$KeepAlive`""

function Register-AegisTask([string]$name, [string[]]$extra) {
    Write-Host "Registering $name"
    $create = @("/Create", "/TN", $name, "/TR", $Tr, "/RL", "LIMITED", "/F") + $extra
    & schtasks.exe @create
    if ($LASTEXITCODE -ne 0) {
        Write-Host "schtasks failed for $name. Run this once:"
        Write-Host ("schtasks.exe " + ($create | ForEach-Object { if ($_ -match '\s') { "`"$_`"" } else { $_ } }) -join " ")
        exit $LASTEXITCODE
    }
}

Register-AegisTask "AegisKeepAliveLogon" @("/SC", "ONLOGON")
Register-AegisTask "AegisKeepAlive" @("/SC", "MINUTE", "/MO", "20")
Write-Host "Registered AegisKeepAliveLogon (on logon) and AegisKeepAlive (every 20 min)."
Write-Host "Daily-loss halt is stored in bot/reports/risk_state.json and survives a restart."
