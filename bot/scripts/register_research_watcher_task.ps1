# Register the AEGIS 20-min research watcher as a resilient current-user task.
#
# Non-admin constraints:
#   - LogonTrigger / ONLOGON / ONSTART require elevation (Access denied),
#     so we use a One-time trigger with an every-20-minute repetition that acts
#     as a self-healing recovery net. The Startup-folder launcher
#     (aegis_research_watcher.cmd) starts the loop immediately at logon.
#   - WakeToRun, StartWhenAvailable, restart-on-failure, IgnoreNew, and no
#     execution-time limit all work as a Limited / Interactive principal.
#   - The watcher itself holds a singleton lock, so no duplicate loops can
#     exist even if the task and the Startup launcher both fire.
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BotRoot = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $BotRoot "..")
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Watcher = Join-Path $BotRoot "scripts\research_fast_watcher.py"
$TaskName = "AegisResearchWatcher"

if (-not (Test-Path $Python)) {
    throw "missing venv python: $Python"
}
if (-not (Test-Path $Watcher)) {
    throw "missing watcher: $Watcher"
}

$action = New-ScheduledTaskAction -Execute $Python -Argument "`"-u`" `"$Watcher`"" -WorkingDirectory $BotRoot

# One-time trigger repeating every 20 minutes for 20 years (effectively
# indefinite but finite, which Task Scheduler requires). When the watcher loop
# is already alive the singleton lock records CYCLE_ALREADY_RUNNING and exits;
# when it died, this trigger restarts it.
$trig = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 20) `
    -RepetitionDuration (New-TimeSpan -Days (20 * 365))

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trig `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered $TaskName"
Write-Host "  action: $Python -u $Watcher"
Write-Host "  trigger: every 20 min (self-healing recovery net; logon start via Startup folder)"
Write-Host "  settings: WakeToRun, StartWhenAvailable, restart x3, IgnoreNew, no time limit"
Write-Host "  singleton lock inside the watcher prevents duplicate loops."