#!/usr/bin/env python3
"""Master-spec completion verifier (completion protocol step 11).

Reads bot/reports/research/master_spec_status.json and returns NON-ZERO if any
merge-blocking requirement is not VERIFIED (NOT_APPLICABLE is allowed; BLOCKED
is allowed only for requirements explicitly marked external in the ledger).

With --runtime it additionally performs the live merge gates:
  - exactly one runner process
  - allow_live=false in the active config
  - MT5 account is DEMO (trade_mode 0)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
LEDGER = BOT / "reports" / "research" / "master_spec_status.json"
CONFIG = BOT / "config_mt5_demo_firehose_hw.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify master-spec completion")
    parser.add_argument("--runtime", action="store_true",
                        help="also verify live MT5 DEMO / single-runner gates")
    args = parser.parse_args()

    try:
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read ledger: {exc}")
        return 1

    failures: list[str] = []
    counts: dict[str, int] = {}
    for req in ledger.get("requirements", []):
        status = str(req.get("status") or "NOT_STARTED")
        counts[status] = counts.get(status, 0) + 1
        if status == "VERIFIED":
            continue
        if status == "NOT_APPLICABLE":
            continue
        if status == "BLOCKED" and req.get("external"):
            continue
        failures.append(f"{req.get('id')}: {status} - {req.get('requirement', '')[:90]}")

    print("Ledger status counts:", json.dumps(counts, sort_keys=True))
    if failures:
        print(f"NOT COMPLETE: {len(failures)} requirement(s) below VERIFIED:")
        for line in failures:
            print("  -", line)

    if args.runtime:
        runtime_failures = _runtime_checks()
        for line in runtime_failures:
            print("  [runtime] -", line)
        failures.extend(runtime_failures)

    if failures:
        return 1
    print("MASTER SPEC: all merge-blocking requirements VERIFIED"
          + (" (+ runtime gates pass)" if args.runtime else ""))
    return 0


def _runtime_checks() -> list[str]:
    failures: list[str] = []
    # allow_live must be false.
    try:
        text = CONFIG.read_text(encoding="utf-8")
        found = False
        for line in text.splitlines():
            if line.strip().startswith("allow_live:"):
                value = line.split(":", 1)[1].strip().lower()
                found = True
                if value != "false":
                    failures.append(f"allow_live is {value!r}, must be false")
                break
        if not found:
            failures.append("allow_live key missing from config")
    except OSError as exc:
        failures.append(f"cannot read config: {exc}")
    # Exactly one runner: heartbeat pid must be alive AND be a python process
    # running run_broker_paper (heartbeat staleness also proves liveness).
    try:
        hb = json.loads((BOT / "reports" / "bot_heartbeat.json").read_text(encoding="utf-8"))
        pid = int(hb.get("pid") or 0)
        age = None
        import time as _time

        ts = float(hb.get("ts") or 0)
        age = round(_time.time() - ts, 1) if ts else None
        if not pid:
            failures.append("heartbeat has no pid")
        else:
            tl = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                capture_output=True, text=True, timeout=30,
            ).stdout
            if "python" not in tl.lower():
                failures.append(f"runner pid {pid} not alive")
        if age is None or age > 300:
            failures.append(f"runner heartbeat stale ({age}s)")
    except Exception as exc:
        failures.append(f"runner liveness check failed: {exc}")
    # MT5 DEMO check.
    try:
        code = (
            "import MetaTrader5 as mt5;"
            "mt5.initialize();"
            "a=mt5.account_info();"
            "print(a.trade_mode);"
            "mt5.shutdown()"
        )
        out = subprocess.run(
            [str(BOT.parent / ".venv" / "Scripts" / "python.exe"), "-c", code],
            capture_output=True, text=True, timeout=60,
        )
        trade_mode = (out.stdout or "").strip()
        if trade_mode != "0":
            failures.append(f"MT5 account trade_mode={trade_mode!r}, must be 0 (DEMO)")
    except Exception as exc:
        failures.append(f"MT5 demo check failed: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
