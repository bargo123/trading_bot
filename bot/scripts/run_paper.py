#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config
from aegis.paper import PaperBot


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Aegis paper bot")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    journal = ROOT / "reports" / str(cfg.get("test_name", "paper") + "_journal.jsonl")
    if "test_name" not in cfg:
        journal = ROOT / "reports" / "paper_journal.jsonl"
    bot = PaperBot(cfg, journal_path=journal)
    if args.once:
        bot.step_once()
        print(f"Equity={bot.broker.equity:.2f} open={bot.broker.position}")
    else:
        print(f"Journal → {journal}")
        bot.run_forever()


if __name__ == "__main__":
    main()
