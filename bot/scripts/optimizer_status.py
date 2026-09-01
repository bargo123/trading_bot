#!/usr/bin/env python3
"""Optimizer / paper-runner status. Read-only; does not shutdown MT5."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402
from aegis.optimizer.state import ensure_memory, live_config_path, load_opt_config  # noqa: E402
from aegis.optimizer.status import build_status  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis optimizer status")
    parser.add_argument("--no-mt5", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    opt_cfg = load_opt_config()
    ensure_memory(opt_cfg)
    cfg = load_config(live_config_path(opt_cfg))
    payload = build_status(cfg, probe_mt5=not args.no_mt5)
    print(json.dumps(payload, default=str, indent=2))


if __name__ == "__main__":
    main()
