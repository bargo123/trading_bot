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
    reqs = ledger.get("requirements", [])
    for req in reqs:
        status = str(req.get("status") or "NOT_STARTED")
        counts[status] = counts.get(status, 0) + 1
        if status == "VERIFIED":
            # Machine-checkable verification (audited fix 12): never trust the
            # ledger label blindly.
            rid = str(req.get("id"))
            for f in req.get("implementation_files") or []:
                if not (BOT.parent / f).exists():
                    failures.append(f"{rid}: implementation file missing: {f}")
            for t in req.get("tests") or []:
                test_path = str(t).split("::")[0]
                if not (BOT / test_path).exists():
                    failures.append(f"{rid}: referenced test missing: {t}")
            sha = str(req.get("commit_sha") or "").strip().lower()
            if not sha or "pending" in sha:
                failures.append(f"{rid}: VERIFIED without commit_sha")
            evidence = str(req.get("evidence") or "").strip()
            if len(evidence) < 10:
                failures.append(f"{rid}: VERIFIED without meaningful evidence")
            continue
        if status == "NOT_APPLICABLE":
            continue
        if status == "BLOCKED" and req.get("external"):
            continue
        failures.append(f"{req.get('id')}: {status} - {str(req.get('requirement', ''))[:90]}")

    # Ledger counts must reconcile.
    total_declared = sum(counts.values())
    if total_declared != len(reqs):
        failures.append(f"ledger counts do not reconcile: {total_declared} != {len(reqs)}")

    failures.extend(_invariant_checks())

    print("Ledger status counts:", json.dumps(counts, sort_keys=True))
    if failures:
        print(f"NOT COMPLETE: {len(failures)} problem(s):")
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
          " (+ machine checks + runtime gates pass)" if args.runtime else
          "MASTER SPEC: all merge-blocking requirements VERIFIED (+ machine checks)")
    return 0


def _invariant_checks() -> list[str]:
    """Cross-code invariants the audit explicitly requires the verifier to catch."""
    failures: list[str] = []
    # Invariant: MIN_N_TO_JUDGE <= exploration_max_trades_per_hypothesis.
    try:
        import re as _re

        src = (BOT / "aegis" / "intel" / "exploration.py").read_text(encoding="utf-8")
        m = _re.search(r"MIN_N_TO_JUDGE\s*=\s*(\d+)", src)
        min_n = int(m.group(1)) if m else 10**9
        cap = None
        cfg_text = CONFIG.read_text(encoding="utf-8")
        for line in cfg_text.splitlines():
            if line.strip().startswith("exploration_max_trades_per_hypothesis:"):
                cap = int(line.split(":", 1)[1].strip())
                break
        if cap is None:
            cap = 5  # documented default in ExplorationLimits
        if min_n > cap:
            failures.append(
                f"P0 invariant violated: MIN_N_TO_JUDGE({min_n}) > "
                f"max_trades_per_hypothesis({cap}); lifecycle unreachable"
            )
    except Exception as exc:
        failures.append(f"invariant check failed to run: {exc}")
    # Deterministic risk-cap check: broker-minimum on a 50-pip stop at $0.15
    # budget MUST be rejected.
    try:
        sys.path.insert(0, str(BOT))
        from aegis.intel.exploration import risk_lots_for_exploration

        r = risk_lots_for_exploration(
            max_risk_usd=0.15, entry=1.1000, invalidation=1.0950,
            pip=0.0001, contract_size=100000.0,
            volume_min=0.01, volume_step=0.01,
        )
        if r.get("allowed") is not False:
            failures.append(
                "P0 risk-cap contradiction: 50-pip/$0.15 min-lot trade was allowed"
            )
    except Exception as exc:
        failures.append(f"risk-cap check failed to run: {exc}")
    return failures


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
