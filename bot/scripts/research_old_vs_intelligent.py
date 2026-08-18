"""Write old vs intelligent scoreboard from the demo journal."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.intel.scoreboard import load_journal, scoreboard_markdown, summarize_journal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--journal",
        default=str(BOT / "reports" / "mt5_demo_firehose_hw_journal.jsonl"),
    )
    parser.add_argument(
        "--out",
        default=str(BOT / "reports" / "research" / "old_vs_intelligent.md"),
    )
    args = parser.parse_args()
    rows = load_journal(Path(args.journal))
    # Tail to keep this cheap on huge journals.
    summary = summarize_journal(rows[-12000:])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(scoreboard_markdown(summary), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"wrote": str(out), "old_closes": summary["old"]["closes"], "fires": summary["intelligent"]["fires"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
