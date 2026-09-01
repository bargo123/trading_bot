#!/usr/bin/env python3
"""Write the research-only strategy-assumption audit; never contacts MT5."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.research.strategy_audit import audit_markdown  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Write intelligence-first strategy audit")
    parser.add_argument(
        "--report",
        type=Path,
        default=BOT / "reports" / "research" / "strategy_assumption_audit.md",
    )
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(audit_markdown(), encoding="utf-8")
    print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
