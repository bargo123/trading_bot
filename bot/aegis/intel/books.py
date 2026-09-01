"""Book-concept index for intel experiments. Digests only — attach full books per chat."""
from __future__ import annotations

from typing import Any

# Weakness → digest + keywords. Full extracts live under docs/trading/books/.
CONCEPTS: dict[str, dict[str, Any]] = {
    "spread_bleed": {
        "file": "docs/trading/NEW_BOOKS_HARRIS_JANSEN.md",
        "books": ["Harris 2002 Trading and Exchanges"],
        "keywords": ["spread", "adverse selection", "market order pays the spread"],
        "concept": "harris_half_spread",
    },
    "chop": {
        "file": "docs/trading/NEW_BOOKS_KAUFMAN_VOLMAN_JOHNSON_CHAN.md",
        "books": ["Kaufman efficiency ratio (digest)"],
        "keywords": ["efficiency ratio", "chop", "ER"],
        "concept": "kaufman_er",
    },
    "false_breakout": {
        "file": "docs/trading/NEW_BOOKS_VPA_BROOKS_DAMIR.md",
        "books": ["Brooks Ranges 2012", "Damir 2016"],
        "keywords": ["failed breakout", "range", "buy low sell high"],
        "concept": "brooks_failed_bo",
    },
    "high_wr_neg_e": {
        "file": "docs/trading/NEW_BOOKS_CORE_TWELVE.md",
        "books": ["Tharp", "Aronson", "Davey"],
        "keywords": ["expectancy", "win rate", "R-multiple"],
        "concept": "tharp_expectancy",
    },
    "late_entry": {
        "file": "docs/trading/NEW_BOOKS_HARRIS_JANSEN.md",
        "books": ["Harris 2002", "Jansen 2018"],
        "keywords": ["jump", "chase", "momentum z"],
        "concept": "harris_jump_jansen_mom",
    },
    "regime": {
        "file": "docs/trading/NEW_BOOKS_CORE_TWELVE.md",
        "books": ["Elder Impulse", "Kaufman ER"],
        "keywords": ["regime", "Impulse", "trend", "range"],
        "concept": "elder_impulse_regime",
    },
    "execution": {
        "file": "docs/trading/NEW_BOOKS_DONADIO_HFT.md",
        "books": ["Donadio/Ghosh/Rossier 2022"],
        "keywords": ["OMS", "stale quote", "tick-to-trade"],
        "concept": "donadio_oms",
    },
    "barbwire": {
        "file": "docs/trading/books/trading-price-action-ranges-brooks.md",
        "books": ["Brooks Ranges 2012"],
        "keywords": ["barbwire", "don't touch", "overlapping dojis"],
        "concept": "brooks_barbwire",
    },
    "exhaustion": {
        "file": "docs/trading/NEW_BOOKS_CORE_TWELVE.md",
        "books": ["Elder Impulse", "Wilder RSI"],
        "keywords": ["impulse against", "RSI extreme", "EMA lag"],
        "concept": "elder_impulse_exhaustion",
    },
    "left_tail": {
        "file": "docs/trading/NEW_BOOKS_CORE_TWELVE.md",
        "books": ["Tharp Trade Your Way", "Harris 2002"],
        "keywords": ["expectancy", "R-multiple", "cut left tail"],
        "concept": "tharp_scratch_overlay",
    },
}


def lookup(weakness: str) -> dict[str, Any]:
    return CONCEPTS.get(str(weakness), CONCEPTS["chop"])
