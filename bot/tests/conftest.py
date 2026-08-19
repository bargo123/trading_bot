"""Make ``aegis`` and ``bot/scripts`` importable for any subset of the suite.

Several test modules import ``aegis...`` at module scope without adjusting
``sys.path`` themselves. That works in a full alphabetical run only because an
earlier module happens to have inserted the path first, so running a single test
file or a hand-picked subset fails to collect. Doing it here makes every test
independently runnable.
"""
from __future__ import annotations

import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]

for path in (BOT, BOT / "scripts"):
    entry = str(path)
    if entry not in sys.path:
        sys.path.insert(0, entry)
