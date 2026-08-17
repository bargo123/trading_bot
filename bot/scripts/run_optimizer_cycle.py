#!/usr/bin/env python3
"""One-shot autonomous optimizer cycle (separate lock from the paper runner)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.optimizer.cycle import run_cycle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis optimizer cycle")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-mt5", action="store_true")
    parser.add_argument("--with-cursor", action="store_true")
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run_cycle(
        dry_run=args.dry_run,
        no_mt5=args.no_mt5,
        with_cursor=args.with_cursor,
        skip_pytest=args.skip_pytest,
    )
    print(json.dumps(result, default=str, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
