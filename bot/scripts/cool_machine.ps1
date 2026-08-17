# Cut laptop heat without touching the trading workflow.
# Does not flatten, does not mt5.shutdown(), does not change YAML / firehose / poll.
# Sleep and hibernate stay Never so the 24h demo keeps running.

param(
    [int]$DisplayOffSecondsAc = 600,
    [int]$DisplayOffSecondsDc = 300,
    [int]$ProcessorMaxPercent = 99
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BotRoot = Resolve-Path (Join-Path $ScriptDir "..")
$LogFile = Join-Path $BotRoot "optimizer\cool_machine.log"

function Write-Log([string]$msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"), $msg
    New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
    Add-Content -Path $LogFile -Value $line
}

function Set-Both([string]$sub, [string]$setting, [int]$ac, [int]$dc) {
    powercfg /SETACVALUEINDEX SCHEME_CURRENT $sub $setting $ac | Out-Null
    powercfg /SETDCVALUEINDEX SCHEME_CURRENT $sub $setting $dc | Out-Null
}

# Keep the machine awake. Only the screen may turn off.
Set-Both "SUB_SLEEP" "STANDBYIDLE" 0 0
Set-Both "SUB_SLEEP" "HIBERNATEIDLE" 0 0
Set-Both "SUB_SLEEP" "UNATTENDSLEEP" 0 0
Set-Both "SUB_SLEEP" "HYBRIDSLEEP" 0 0

# Screen off is free heat reduction; moving the mouse brings it back.
Set-Both "SUB_VIDEO" "VIDEOIDLE" $DisplayOffSecondsAc $DisplayOffSecondsDc

# 99% max state drops Intel turbo on this i5-1235U. Base clock is enough for 1s paper polls.
$max = [Math]::Max(50, [Math]::Min(99, $ProcessorMaxPercent))
Set-Both "SUB_PROCESSOR" "PROCTHROTTLEMAX" $max $max
Set-Both "SUB_PROCESSOR" "PROCTHROTTLEMIN" 5 5

# Boost mode 0 = Disabled (ignore if this GUID is missing on the plan).
powercfg /SETACVALUEINDEX SCHEME_CURRENT SUB_PROCESSOR PERFBOOSTMODE 0 2>$null | Out-Null
powercfg /SETDCVALUEINDEX SCHEME_CURRENT SUB_PROCESSOR PERFBOOSTMODE 0 2>$null | Out-Null

# Prefer efficiency when the CPU has a choice. Higher = cooler, still runs the same work.
powercfg /SETACVALUEINDEX SCHEME_CURRENT SUB_PROCESSOR PERFEPP 70 2>$null | Out-Null
powercfg /SETDCVALUEINDEX SCHEME_CURRENT SUB_PROCESSOR PERFEPP 90 2>$null | Out-Null

# Active cooling: fans work before the package cooks. 1 = Active, 0 = Passive.
Set-Both "SUB_PROCESSOR" "SYSCOOLPOL" 1 1

# ASPM on the iGPU link when idle.
powercfg /SETACVALUEINDEX SCHEME_CURRENT SUB_PCIEXPRESS ASPM 1 2>$null | Out-Null
powercfg /SETDCVALUEINDEX SCHEME_CURRENT SUB_PCIEXPRESS ASPM 2 2>$null | Out-Null

powercfg /SETACTIVE SCHEME_CURRENT | Out-Null

# Research only: optimizer / pytest. Never the paper runner (run_broker_paper.py) or MT5.
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match 'run_optimizer_cycle\.py' -or
            $_.CommandLine -match 'pytest'
        ) -and ($_.CommandLine -notmatch 'run_broker_paper\.py')
    } |
    ForEach-Object {
        try {
            $p = Get-Process -Id $_.ProcessId -ErrorAction Stop
            if ($p.PriorityClass -ne [System.Diagnostics.ProcessPriorityClass]::Idle) {
                $p.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
            }
        } catch {}
    }

Write-Log "cool_machine applied processor_max=${max}% display_ac=${DisplayOffSecondsAc}s sleep=never"
Write-Host "Cool settings applied: turbo capped at ${max}%, screen off ${DisplayOffSecondsAc}s AC, sleep still Never."
Write-Host "Paper runner, MT5, firehose YAML, and poll interval were not changed."
exit 0
