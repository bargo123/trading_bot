# Register a current-user logon scheduled task for the optimizer supervisor.
# Not a privileged Windows service. If schtasks is denied, the exact command is printed.

param(
    [int]$IntervalMinutes = 20
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Supervisor = Join-Path $ScriptDir "supervisor_optimizer.ps1"
$TaskName = "AegisOptimizer"
$Tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Supervisor`" -IntervalMinutes $IntervalMinutes"

Write-Host "Registering current-user logon task $TaskName"
Write-Host $Tr

$create = @(
    "/Create",
    "/TN", $TaskName,
    "/TR", $Tr,
    "/SC", "ONLOGON",
    "/RL", "LIMITED",
    "/F"
)

& schtasks.exe @create
if ($LASTEXITCODE -ne 0) {
    Write-Host "schtasks failed. Run this once in an elevated or allowed prompt:"
    Write-Host ("schtasks.exe " + ($create | ForEach-Object { if ($_ -match '\s') { "`"$_`"" } else { $_ } }) -join " ")
    exit $LASTEXITCODE
}
Write-Host "Registered. The live paper runner is separate; this only loops the optimizer cycle."
