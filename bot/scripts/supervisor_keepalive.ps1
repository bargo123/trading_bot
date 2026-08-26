param(
    [switch]$Loop,
    [int]$IntervalSeconds = 1200
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BotRoot = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $BotRoot "..")
# venv lives at repo root (bot/.venv is not created by the setup scripts)
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$LogFile = Join-Path $BotRoot "optimizer\keepalive.log"
$PaperCfg = "config_mt5_demo_firehose_hw.yaml"
$Mt5Path = "C:\Program Files\MetaTrader 5\terminal64.exe"
$FirehoseStop = Join-Path $BotRoot "reports\FIREHOSE_STOP"

function Write-Log([string]$msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"), $msg
    New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
    Add-Content -Path $LogFile -Value $line
}

function Test-CmdMatch([string]$pattern) {
    $hit = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match $pattern) }
    return [bool]$hit
}

function Ensure-MT5 {
    if (Get-Process -Name "terminal64" -ErrorAction SilentlyContinue) {
        return
    }
    if (-not (Test-Path $Mt5Path)) {
        Write-Log "MT5 not found: $Mt5Path"
        return
    }
    Write-Log "starting MetaTrader 5 after shutdown/logon"
    Start-Process -FilePath $Mt5Path
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        if (Get-Process -Name "terminal64" -ErrorAction SilentlyContinue) {
            Start-Sleep -Seconds 20
            return
        }
        Start-Sleep -Seconds 2
    }
    Write-Log "MT5 did not appear within 90s; paper runner will retry next loop"
}

function Invoke-KeepAlive {
    if (-not (Test-Path $Python)) {
        Write-Log "missing venv python: $Python"
        return
    }

    if (Test-Path $FirehoseStop) {
        Write-Log "[FIREHOSE] STOP FIREHOSE marker present; not restarting runner"
        return
    }

    $cool = Join-Path $ScriptDir "cool_machine.ps1"
    if (Test-Path $cool) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $cool | Out-Null
    }

    Ensure-MT5

    if (-not (Test-CmdMatch "run_broker_paper\.py")) {
        Write-Log "paper runner down; starting $PaperCfg"
        Start-Process -FilePath $Python -ArgumentList @(
            "-u", "scripts\run_broker_paper.py", "--config", $PaperCfg,
            "--video-style"
        ) -WorkingDirectory $BotRoot -WindowStyle Hidden
    }

    $supPidFile = Join-Path $BotRoot "optimizer\supervisor.pid"
    $supAlive = $false
    if (Test-Path $supPidFile) {
        $old = (Get-Content $supPidFile | Select-Object -First 1).Trim()
        if ($old -match '^\d+$') {
            $supAlive = [bool](Get-Process -Id ([int]$old) -ErrorAction SilentlyContinue)
        }
    }
    if (-not $supAlive) {
        Write-Log "optimizer supervisor down; starting"
        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $ScriptDir "supervisor_optimizer.ps1")
        ) -WorkingDirectory $RepoRoot -WindowStyle Hidden
    }
}

Invoke-KeepAlive
if ($Loop) {
    Write-Log "keepalive loop interval=${IntervalSeconds}s"
    while ($true) {
        Start-Sleep -Seconds ([Math]::Max(60, $IntervalSeconds))
        Invoke-KeepAlive
    }
}
exit 0
