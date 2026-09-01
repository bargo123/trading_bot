"""Read-only research observation. Does not place orders or start a runner."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.research.observe import observe_from_paths  # noqa: E402
from aegis.research.paths import DEFAULT_REGISTRY  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Observe champion/heartbeat; never trades")
    p.add_argument("--heartbeat", type=Path, default=BOT / "reports" / "bot_heartbeat.json")
    p.add_argument("--db", type=Path, default=DEFAULT_REGISTRY)
    args = p.parse_args()
    out = observe_from_paths(heartbeat_path=args.heartbeat, db_path=args.db)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
