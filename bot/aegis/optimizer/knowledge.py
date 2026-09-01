"""Map live weaknesses to a single digest/book file. Do not dump the library."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from aegis.optimizer.paths import REPO_ROOT
from aegis.optimizer.state import BOOK_CONCEPTS, OPTIMIZER_DIR, read_json, write_json

WEAKNESS_MAP: dict[str, dict[str, Any]] = {
    "spread_bleed": {
        "file": "docs/trading/NEW_BOOKS_HFT_CARTEA_ALDRIDGE_ORESTE_NARANG_VANDERPOST.md",
        "keywords": ["spread", "transaction cost", "Harris", "scalp"],
        "concept": "harris_spread_gate",
    },
    "chop": {
        "file": "docs/trading/NEW_BOOKS_KAUFMAN_VOLMAN_JOHNSON_CHAN.md",
        "keywords": ["efficiency ratio", "Kaufman", "ER", "chop"],
        "concept": "kaufman_er",
    },
    "high_wr_neg_e": {
        "file": "docs/trading/NEW_BOOKS_CORE_TWELVE.md",
        "keywords": ["expectancy", "Tharp", "win rate"],
        "concept": "tharp_expectancy",
    },
    "impulse_censor": {
        "file": "docs/trading/NEW_BOOKS_CORE_TWELVE.md",
        "keywords": ["Impulse", "Elder", "censor"],
        "concept": "elder_impulse_censor",
    },
    "correlation_cluster": {
        "file": "docs/trading/NEW_BOOKS_CORE_TWELVE.md",
        "keywords": ["Diversification", "correlation", "Clenow"],
        "concept": "davey_clenow_correlation",
    },
    "session_clock": {
        "file": "docs/trading/NEW_BOOKS_AEGIS_MT5_FOREX_BATCH.md",
        "keywords": ["London–NY", "thin hours", "Silvani"],
        "concept": "silvani_session_clock",
    },
}


def mapped_path(weakness: str) -> Path | None:
    spec = WEAKNESS_MAP.get(weakness)
    if not spec:
        return None
    path = REPO_ROOT / str(spec["file"])
    return path if path.exists() else None


def snippet_for(path: Path, keywords: list[str], max_chars: int = 400) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    idx = -1
    hit = ""
    for kw in keywords:
        idx = lowered.find(kw.lower())
        if idx >= 0:
            hit = kw
            break
    if idx < 0:
        snippet = text[:max_chars]
    else:
        start = max(0, idx - 80)
        snippet = text[start : start + max_chars]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    digest = hashlib.sha256(snippet.encode("utf-8", errors="replace")).hexdigest()[:16]
    return snippet, digest + (f":{hit}" if hit else "")


def lookup_concept(weakness: str) -> dict[str, Any]:
    spec = WEAKNESS_MAP.get(weakness) or WEAKNESS_MAP["high_wr_neg_e"]
    path = REPO_ROOT / str(spec["file"])
    snippet, digest = ("", "")
    if path.exists():
        snippet, digest = snippet_for(path, list(spec["keywords"]))
    return {
        "weakness": weakness,
        "book_file": str(spec["file"]),
        "concept": spec["concept"],
        "snippet": snippet,
        "snippet_hash": digest,
    }


def mark_investigated(concept: str, book_file: str) -> None:
    path = OPTIMIZER_DIR / BOOK_CONCEPTS
    data = read_json(path, {"investigated": []}) or {"investigated": []}
    rows = list(data.get("investigated") or [])
    if not any(r.get("concept") == concept for r in rows):
        rows.append({"concept": concept, "book_file": book_file})
    data["investigated"] = rows
    write_json(path, data)
