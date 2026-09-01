$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BotRoot = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $BotRoot "..")
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Request = Join-Path $RepoRoot ".ai-bridge\verification-request.json"
$Result = Join-Path $RepoRoot ".ai-bridge\verification-result.json"
$self = $MyInvocation.MyCommand.Path

try {
    if (-not (Test-Path $Request)) { exit 0 }
    $req = Get-Content -Raw -Path $Request | ConvertFrom-Json
    if ([string]$req.mode -ne "finish_governed") { exit 0 }
    if (-not (Test-Path $Python)) { throw "missing repo venv python: $Python" }

    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    Push-Location $BotRoot
    try {
        $testOutput = (& $Python -m pytest -q 2>&1 | Out-String)
        $testRc = $LASTEXITCODE
    } finally { Pop-Location }
    $timer.Stop()

    $out = [ordered]@{
        mode = "finish_governed"
        returncode = [int]$testRc
        elapsed_s = [Math]::Round($timer.Elapsed.TotalSeconds, 2)
        stdout = [string]$testOutput
        stderr = ""
        restart_requested = $false
        helpers_removed = @()
    }
    if ($testRc -ne 0) {
        $out | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -Path $Result
        Remove-Item -Force $Request -ErrorAction SilentlyContinue
        exit $testRc
    }

    $probeCode = 'import json, MetaTrader5 as mt5; ok=bool(mt5.initialize()); a=mt5.account_info() if ok else None; p=mt5.positions_get() if ok else (); print(json.dumps({"ok":ok,"trade_mode":int(getattr(a,"trade_mode",-1)) if a is not None else -1,"server":str(getattr(a,"server","")) if a is not None else "","positions":len(p or ())})); mt5.shutdown() if ok else None'
    $mt5Raw = (& $Python -c $probeCode 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "MT5 read-only probe failed: $mt5Raw" }
    $mt5 = $mt5Raw | ConvertFrom-Json
    $out.mt5 = $mt5
    if (-not [bool]$mt5.ok) { throw "MT5 not connected" }
    if ([int]$mt5.trade_mode -ne 0) { throw "MT5 account is not DEMO" }
    if ([int]$mt5.positions -ne 0) { throw "MT5 not flat" }

    $heartbeatPath = Join-Path $BotRoot "reports\bot_heartbeat.json"
    $hb = Get-Content -Raw -Path $heartbeatPath | ConvertFrom-Json
    if ([int]$hb.open -ne 0) { throw "runner heartbeat not flat" }
    $runnerPid = [int]$hb.pid
    $watcherLock = Join-Path $BotRoot "research\fast_watcher_state\watcher.lock"
    $watcherPid = 0
    if (Test-Path $watcherLock) {
        $raw = (Get-Content $watcherLock | Select-Object -First 1).Trim()
        if ($raw -match '^\d+$') { $watcherPid = [int]$raw }
    }
    if ($runnerPid -le 0 -or $watcherPid -le 0) { throw "could not resolve runner/watcher owner pids" }

    $runnerProc = Get-CimInstance Win32_Process -Filter "ProcessId=$runnerPid" -ErrorAction SilentlyContinue
    $watcherProc = Get-CimInstance Win32_Process -Filter "ProcessId=$watcherPid" -ErrorAction SilentlyContinue
    if (-not $runnerProc -or -not $runnerProc.CommandLine -or $runnerProc.CommandLine -notmatch 'run_broker_paper\.py' -or $runnerProc.CommandLine -notmatch '--video-style') { throw "runner identity mismatch pid=$runnerPid" }
    if (-not $watcherProc -or -not $watcherProc.CommandLine -or $watcherProc.CommandLine -notmatch 'research_fast_watcher\.py') { throw "watcher identity mismatch pid=$watcherPid" }
    $out.old_runner_pid = $runnerPid
    $out.old_watcher_pid = $watcherPid

    $helpers = @(
        (Join-Path $RepoRoot "_temp_check.py"),
        (Join-Path $BotRoot "add_calculate_metrics.py"),
        (Join-Path $BotRoot "add_calculate_metrics2.py"),
        (Join-Path $BotRoot "add_method.py"),
        (Join-Path $BotRoot "add_research_cycle.py"),
        (Join-Path $BotRoot "add_test_method.py"),
        (Join-Path $BotRoot "fix_add_method.py"),
        (Join-Path $BotRoot "fix_final.py"),
        (Join-Path $BotRoot "fix_hypothesis.py"),
        (Join-Path $BotRoot "fix_hypothesis_dataclass.py"),
        (Join-Path $BotRoot "fix_hypothesis_gen.py"),
        (Join-Path $BotRoot "fix_hypothesis_v2.py"),
        (Join-Path $BotRoot "fix_imports.py"),
        (Join-Path $BotRoot "fix_method3.py"),
        (Join-Path $BotRoot "fix_return.py"),
        (Join-Path $BotRoot "fix_syntax.py"),
        (Join-Path $BotRoot "fix_syntax_final.py"),
        (Join-Path $BotRoot "fix_test.py"),
        (Join-Path $BotRoot "fix_test2.py")
    )
    foreach ($helper in $helpers) {
        if (Test-Path $helper) {
            Remove-Item -Force $helper
            $out.helpers_removed += [string]$helper
        }
    }

    Stop-Process -Id $runnerPid -Force -ErrorAction Stop
    Stop-Process -Id $watcherPid -Force -ErrorAction Stop
    Start-Sleep -Seconds 2
    Start-ScheduledTask -TaskName "AegisResearchWatcher" -ErrorAction Stop
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ScriptDir "supervisor_keepalive.ps1") | Out-Null
    $out.restart_requested = $true

    $deadline = (Get-Date).AddSeconds(45)
    $fresh = $null
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 1
        try {
            $candidate = Get-Content -Raw -Path $heartbeatPath | ConvertFrom-Json
            if ([int]$candidate.pid -ne $runnerPid -and [string]$candidate.status -eq "running" -and [int]$candidate.open -eq 0) { $fresh = $candidate; break }
        } catch {}
    }
    if (-not $fresh) { throw "fresh governed broker heartbeat not observed within 45s" }

    $runnerOwners = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -match 'run_broker_paper\.py' })
    $watcherOwners = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -match 'research_fast_watcher\.py' })
    $out.runner_owner_count = $runnerOwners.Count
    $out.watcher_owner_count = $watcherOwners.Count
    $out.fresh_runner = [ordered]@{ pid=[int]$fresh.pid; status=[string]$fresh.status; open=[int]$fresh.open; short_horizon_model=[string]$fresh.short_horizon_model.execution_status }
    if ($runnerOwners.Count -ne 1) { throw "expected exactly one broker owner, found $($runnerOwners.Count)" }
    if ($watcherOwners.Count -ne 1) { throw "expected exactly one watcher owner, found $($watcherOwners.Count)" }

    $out.returncode = 0
    $out | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -Path $Result
    Remove-Item -Force $Request -ErrorAction SilentlyContinue
    exit 0
}
catch {
    $failure = [ordered]@{ mode="finish_governed"; returncode=125; elapsed_s=0; stdout=""; stderr=$_.Exception.Message; restart_requested=$false }
    try { $failure | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -Path $Result } catch {}
    Remove-Item -Force $Request -ErrorAction SilentlyContinue
    exit 125
}
finally {
    Remove-Item -Force $self -ErrorAction SilentlyContinue
}
