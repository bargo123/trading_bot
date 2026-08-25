"""Continuously refresh the read-only universal fast-edge shadow generation."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


BOT_ROOT = Path(__file__).resolve().parents[1]
WORKER = Path(__file__).resolve().with_name("research_fast_edge_shadow.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=BOT_ROOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--out-dir", type=Path, default=BOT_ROOT / "reports" / "research")
    parser.add_argument("--lookback-seconds", type=int, default=3600)
    parser.add_argument("--sample-every-seconds", type=int, default=5)
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--council", action="store_true", help="run the bounded research-only Council handoff after each generation")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    while True:
        generation = args.out_dir / "fast_edge_generations" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        generation.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable, str(WORKER),
            "--config", str(args.config),
            "--out-dir", str(generation),
            "--lookback-seconds", str(max(60, int(args.lookback_seconds))),
            "--sample-every-seconds", str(max(1, int(args.sample_every_seconds))),
            "--no-rows",
        ]
        result = subprocess.run(command, cwd=str(BOT_ROOT.parent), check=False)
        latest = generation / "fast_edge_leaderboard.json"
        if result.returncode == 0 and latest.exists():
            shutil.copy2(latest, args.out_dir / "fast_edge_leaderboard.json")
            handoff = generation / "fast_edge_factory_handoff.json"
            if handoff.exists():
                shutil.copy2(handoff, args.out_dir / "fast_edge_factory_handoff.json")
            if args.council:
                subprocess.run(
                    [
                        sys.executable,
                        str(BOT_ROOT / "scripts" / "review_fast_edge_council.py"),
                        "--report", str(latest),
                        "--output", str(generation / "fast_edge_council_review.json"),
                    ],
                    cwd=str(BOT_ROOT.parent), check=False,
                )
        if args.once:
            return int(result.returncode)
        time.sleep(max(60, int(args.interval_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
