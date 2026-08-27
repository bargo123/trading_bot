$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BotRoot = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $BotRoot "..")
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Request = Join-Path $RepoRoot ".ai-bridge\shadow-exploration-reload.json"
$Result = Join-Path $RepoRoot ".ai-bridge\shadow-exploration-reload-result.json"
$PaperCfg = "config_mt5_demo_firehose_hw.yaml"

if (-not (Test-Path $Request)) { exit 0 }
$out = [ordered]@{
    mode = "shadow_exploration_reload"
    returncode = 125
    restarted = $false
    old_runner_pid = 0
    new_runner_pid = 0
    tests = ""
    stderr = ""
}
try {
    if (-not (Test-Path $Python)) { throw "missing repo venv python" }

    Push-Location $BotRoot
    try {
        $testOutput = (& $Python -m pytest `
            tests/test_short_horizon_firehose_gate.py `
            tests/test_exploration_firehose.py `
            tests/test_intel_firehose_brain.py -q 2>&1 | Out-String)
        $testRc = $LASTEXITCODE
    }
    finally { Pop-Location }
    $out.tests = [string]$testOutput
    if ($testRc -ne 0) { throw "focused pytest failed rc=$testRc" }

    $probeCode = 'import json; from aegis.config import load_config; from aegis.engines import create_engine; c=load_config("config_mt5_demo_firehose_hw.yaml"); e=create_engine({**c,"allow_live":False}); e.connect_readonly(); a=e.account(); p=e.positions(); print(json.dumps({"allow_live":bool(c.get("allow_live",False)),"mode":str(c.get("mode","")),"paper":bool(getattr(a,"is_paper",False)),"positions":len(p)})); e.disconnect()'
    Push-Location $BotRoot
    try {
        $probeRaw = (& $Python -c $probeCode 2>&1 | Out-String).Trim()
        $probeRc = $LASTEXITCODE
    }
    finally { Pop-Location }
    if ($probeRc -ne 0) { throw "DEMO read-only probe failed: $probeRaw" }
    $probe = $probeRaw | ConvertFrom-Json
    $out.probe = $probe
    if ([bool]$probe.allow_live) { throw "refusing reload: allow_live=true" }
    if ([string]$probe.mode -ne "mt5_demo") { throw "refusing reload: mode is not mt5_demo" }
    if (-not [bool]$probe.paper) { throw "refusing reload: MT5 account is not DEMO/paper" }
    if ([int]$probe.positions -ne 0) { throw "refusing reload: MT5 has open positions" }

    $owners = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'run_broker_paper\.py' })
    if ($owners.Count -lt 1) { throw "refusing reload: no broker owner found" }

    $heartbeatPath = Join-Path $BotRoot "reports\bot_heartbeat.json"
    $heartbeat = Get-Content -Raw -Path $heartbeatPath | ConvertFrom-Json
    if ([int]$heartbeat.open -ne 0) { throw "refusing reload: broker heartbeat is not flat" }
    $ownerPids = @($owners | ForEach-Object { [int]$_.ProcessId })
    if ($ownerPids -notcontains [int]$heartbeat.pid) { throw "refusing reload: heartbeat PID is not an audited broker owner" }

    $verifiedOwners = @()
    foreach ($owner in $owners) {
        $cmd = [string]$owner.CommandLine
        if ($cmd -notmatch 'run_broker_paper\.py' -or $cmd -notmatch '--config' -or $cmd -notmatch 'config_mt5_demo_firehose_hw\.yaml') {
            throw "refusing reload: unexpected broker owner command pid=$($owner.ProcessId): $cmd"
        }
        if ($cmd -match '(?i)allow_live|--live') {
            throw "refusing reload: live-like broker owner command pid=$($owner.ProcessId): $cmd"
        }
        $verifiedOwners += $owner
    }

    $out.old_runner_pid = [int]$heartbeat.pid
    $out.stale_runner_pids = @($verifiedOwners | ForEach-Object { [int]$_.ProcessId })
    $out.stale_runner_commands = @($verifiedOwners | ForEach-Object { [string]$_.CommandLine })
    foreach ($owner in $verifiedOwners) {
        Stop-Process -Id ([int]$owner.ProcessId) -Force -ErrorAction Stop
    }
    Start-Sleep -Seconds 2

    $remaining = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'run_broker_paper\.py' })
    if ($remaining.Count -ne 0) { throw "refusing handoff: stale broker owner still present after cleanup" }

    # Do not start the broker here. This script is invoked by supervisor_keepalive.ps1;
    # after this successful cleanup returns, the supervisor's normal governed path
    # starts exactly one runner with --video-style.
    $out.restarted = $false
    $out.returncode = 0
}
catch {
    $out.stderr = $_.Exception.Message
}
finally {
    $out | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -Path $Result
    Remove-Item -Force $Request -ErrorAction SilentlyContinue
}
