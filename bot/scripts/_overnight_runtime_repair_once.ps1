$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BotRoot = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $BotRoot "..")
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Request = Join-Path $RepoRoot ".ai-bridge\overnight-runtime-repair.json"
$Result = Join-Path $RepoRoot ".ai-bridge\overnight-runtime-repair-result.json"
$HeartbeatPath = Join-Path $BotRoot "reports\bot_heartbeat.json"
$ConfigPath = Join-Path $BotRoot "config_mt5_demo_firehose_hw.yaml"
$TempBashShim = Join-Path $RepoRoot "bash.cmd"

if (-not (Test-Path $Request)) { exit 0 }

$out = [ordered]@{
    mode = "broker_only_stale_owner_cleanup"
    returncode = 125
    cleanup_complete = $false
    focused_tests = ""
    mt5 = $null
    heartbeat_before = $null
    broker_before = @()
    stopped_broker_pids = @()
    broker_after_cleanup = @()
    watcher_processes_untouched = @()
    stderr = ""
}

function Get-MatchingProcesses([string]$pattern) {
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match $pattern) } |
        ForEach-Object {
            [ordered]@{
                pid = [int]$_.ProcessId
                parent_pid = [int]$_.ParentProcessId
                executable = [string]$_.ExecutablePath
                command_line = [string]$_.CommandLine
            }
        })
}

try {
    if (-not (Test-Path $Python)) { throw "missing repo venv python: $Python" }
    if (-not (Test-Path $ConfigPath)) { throw "missing DEMO config: $ConfigPath" }

    # Keep verification bounded to the broker/supervisor and signal-gate surface.
    Push-Location $BotRoot
    try {
        $focused = (& $Python -m pytest `
            tests/test_supervisor_keepalive.py `
            tests/test_short_horizon_firehose_gate.py `
            tests/test_paper_control.py `
            tests/test_watcher_audit.py -q 2>&1 | Out-String)
        $focusedRc = $LASTEXITCODE
    }
    finally { Pop-Location }
    $out.focused_tests = [string]$focused
    if ($focusedRc -ne 0) { throw "focused pytest failed rc=$focusedRc" }

    # Fail closed on config. This repair never edits trading config.
    $cfgRaw = Get-Content -Raw -Path $ConfigPath
    if ($cfgRaw -notmatch '(?m)^mode:\s*mt5_demo\s*$') { throw "refusing cleanup: mode is not mt5_demo" }
    if ($cfgRaw -notmatch '(?m)^allow_live:\s*false\s*$') { throw "refusing cleanup: allow_live is not false" }
    if ($cfgRaw -notmatch '(?m)^paper_trading_enabled:\s*true\s*$') { throw "refusing cleanup: paper_trading_enabled is not true" }

    # Independent read-only MT5 proof immediately before process mutation.
    $probeCode = 'import json, MetaTrader5 as mt5; ok=bool(mt5.initialize()); a=mt5.account_info() if ok else None; p=mt5.positions_get() if ok else (); print(json.dumps({"ok":ok,"trade_mode":int(getattr(a,"trade_mode",-1)) if a is not None else -1,"server":str(getattr(a,"server","")) if a is not None else "","positions":len(p or ())})); mt5.shutdown() if ok else None'
    Push-Location $BotRoot
    try {
        $probeRaw = (& $Python -c $probeCode 2>&1 | Out-String).Trim()
        $probeRc = $LASTEXITCODE
    }
    finally { Pop-Location }
    if ($probeRc -ne 0) { throw "MT5 read-only probe failed: $probeRaw" }
    $probe = $probeRaw | ConvertFrom-Json
    $out.mt5 = $probe
    if (-not [bool]$probe.ok) { throw "refusing cleanup: MT5 not connected" }
    if ([int]$probe.trade_mode -ne 0) { throw "refusing cleanup: MT5 account is not DEMO" }
    if ([string]$probe.server -notmatch '(?i)demo') { throw "refusing cleanup: MT5 server is not DEMO" }
    if ([int]$probe.positions -ne 0) { throw "refusing cleanup: MT5 has open positions" }

    $heartbeat = Get-Content -Raw -Path $HeartbeatPath | ConvertFrom-Json
    $out.heartbeat_before = $heartbeat
    if ([int]$heartbeat.open -ne 0) { throw "refusing cleanup: broker heartbeat is not flat" }

    $brokers = Get-MatchingProcesses 'run_broker_paper\.py'
    $watchers = Get-MatchingProcesses 'research_fast_watcher\.py'
    $out.broker_before = $brokers
    $out.watcher_processes_untouched = $watchers
    if ($brokers.Count -lt 1) { throw "refusing cleanup: no broker owner found" }
    $brokerPids = @($brokers | ForEach-Object { [int]$_.pid })
    if ($brokerPids -notcontains [int]$heartbeat.pid) { throw "refusing cleanup: heartbeat PID is not an audited broker owner" }

    foreach ($broker in $brokers) {
        $cmd = [string]$broker.command_line
        if ($cmd -notmatch 'run_broker_paper\.py' -or $cmd -notmatch '--config' -or $cmd -notmatch 'config_mt5_demo_firehose_hw\.yaml') {
            throw "refusing cleanup: unexpected broker command pid=$($broker.pid): $cmd"
        }
        if ($cmd -match '(?i)allow_live|--live') {
            throw "refusing cleanup: live-like broker command pid=$($broker.pid): $cmd"
        }
    }

    $alreadyCorrect = ($brokers.Count -eq 1 -and [string]$brokers[0].command_line -match '--video-style')
    if (-not $alreadyCorrect) {
        # This is the only process mutation: stop every verified stale/duplicate broker owner.
        # Watcher/Council/Factory processes are deliberately untouched.
        foreach ($broker in $brokers) {
            $pidToStop = [int]$broker.pid
            $existing = Get-Process -Id $pidToStop -ErrorAction SilentlyContinue
            if ($null -eq $existing) {
                continue
            }
            Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 300
            if (Get-Process -Id $pidToStop -ErrorAction SilentlyContinue) {
                throw "cleanup failed: broker owner pid=$pidToStop still alive after Stop-Process"
            }
            $out.stopped_broker_pids += $pidToStop
        }
        Start-Sleep -Seconds 2

        $remaining = Get-MatchingProcesses 'run_broker_paper\.py'
        $out.broker_after_cleanup = $remaining
        if ($remaining.Count -ne 0) { throw "cleanup incomplete: a broker owner remains" }
    }
    else {
        $out.broker_after_cleanup = $brokers
    }

    # This helper is called from cool_machine.ps1 inside supervisor_keepalive.ps1.
    # When cleanup was needed, return with zero broker owners so the supervisor's
    # existing governed path starts exactly one --video-style runner. If already
    # correct, leave the single owner untouched. Do not direct-start it here.
    $out.cleanup_complete = $true
    $out.returncode = 0
}
catch {
    $out.stderr = $_.Exception.Message
}
finally {
    New-Item -ItemType Directory -Force -Path (Split-Path $Result) | Out-Null
    $out | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 -Path $Result
    Remove-Item -Force $Request -ErrorAction SilentlyContinue
    Remove-Item -Force $TempBashShim -ErrorAction SilentlyContinue
}
