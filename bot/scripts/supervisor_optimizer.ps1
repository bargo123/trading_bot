# Requires: PowerShell 5+. Run from anywhere; it locates the repo from this script path.
# Loops run_optimizer_cycle.py. Does not start a second supervisor. Does not flatten trades.

param(
    [int]$IntervalMinutes = 20,
    [int]$InitialSleepSeconds = 0,
    [switch]$DryRun,
    [switch]$NoMt5,
    [switch]$WithCursor
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BotRoot = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $BotRoot "..")
$OptDir = Join-Path $BotRoot "optimizer"
$PidFile = Join-Path $OptDir "supervisor.pid"
$LogFile = Join-Path $OptDir "supervisor.log"
$Python = Join-Path $BotRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

New-Item -ItemType Directory -Force -Path $OptDir | Out-Null

if (Test-Path $PidFile) {
    $old = (Get-Content $PidFile | Select-Object -First 1).Trim()
    if ($old -match '^\d+$') {
        $proc = Get-Process -Id ([int]$old) -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "optimizer supervisor already running pid=$old"
            exit 0
        }
    }
}
Set-Content -Path $PidFile -Value $PID -Encoding ascii

function Write-Log([string]$msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"), $msg
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

$cycle = Join-Path $ScriptDir "run_optimizer_cycle.py"
$flags = @()
if ($DryRun) { $flags += "--dry-run" }
if ($NoMt5) { $flags += "--no-mt5" }
if ($WithCursor) { $flags += "--with-cursor" }

# Cap BLAS/OpenMP so a backtest does not pin every P-core. Same YAML, cooler package.
$env:OMP_NUM_THREADS = "2"
$env:MKL_NUM_THREADS = "2"
$env:OPENBLAS_NUM_THREADS = "2"
$env:NUMEXPR_NUM_THREADS = "2"
$env:VECLIB_MAXIMUM_THREADS = "2"

Write-Log "supervisor start interval=${IntervalMinutes}m python=$Python repo=$RepoRoot cool_threads=2"
try {
    if ($InitialSleepSeconds -gt 0) {
        Write-Log "initial sleep ${InitialSleepSeconds}s (preserve cadence)"
        Start-Sleep -Seconds $InitialSleepSeconds
    }
    while ($true) {
        Write-Log "cycle begin"
        $p = Start-Process -FilePath $Python -ArgumentList (@("-u", $cycle) + $flags) -WorkingDirectory $BotRoot -PassThru -NoNewWindow
        try {
            $p.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
        } catch {}
        Wait-Process -Id $p.Id
        $code = $p.ExitCode
        Write-Log "cycle exit=$code"
        Start-Sleep -Seconds ([Math]::Max(60, $IntervalMinutes * 60))
    }
}
finally {
    if (Test-Path $PidFile) {
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
    Write-Log "supervisor stop"
}
