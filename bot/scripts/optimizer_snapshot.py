#!/usr/bin/env python3
"""Read-only MT5 + journal snapshot. Does not shutdown the terminal."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402
from aegis.optimizer.snapshot import collect_snapshot  # noqa: E402
from aegis.optimizer.state import ensure_memory, live_config_path, load_opt_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis optimizer snapshot (no MT5 shutdown)")
    parser.add_argument("--config", default="")
    parser.add_argument("--no-mt5", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    opt_cfg = load_opt_config()
    ensure_memory(opt_cfg)
    cfg_path = Path(args.config) if args.config else live_config_path(opt_cfg)
    cfg = load_config(cfg_path)
    days = args.lookback_days or int(opt_cfg.get("lookback_days") or 14)
    payload = collect_snapshot(cfg, no_mt5=args.no_mt5, lookback_days=days)
    print(json.dumps({k: payload[k] for k in payload if k not in {"deals", "orders"}}, default=str, indent=2))


if __name__ == "__main__":
    main()
