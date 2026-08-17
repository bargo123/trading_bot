#!/usr/bin/env python3
"""Copy accepted.yaml over the live runner config only when heartbeat shows flat."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.optimizer.promote import promote_if_flat  # noqa: E402
from aegis.optimizer.state import ensure_memory, live_config_path, load_opt_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote accepted optimizer YAML if the bot is flat")
    parser.add_argument("--no-restart", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    opt_cfg = load_opt_config()
    ensure_memory(opt_cfg)
    result = promote_if_flat(
        live_config=live_config_path(opt_cfg),
        restart=not args.no_restart,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, default=str, indent=2))
    if result.get("open", 0) > 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
