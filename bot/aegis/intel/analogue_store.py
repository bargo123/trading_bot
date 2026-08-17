"""Runtime analogue lookup. Loads pre-built index; never imports research."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

import pandas as pd

from aegis.intel.expected_value import payoff_metrics

DEFAULT_ANALOGUE_PATH = Path(__file__).resolve().parents[2] / "intel" / "analogue_index.json"


@dataclass(frozen=True)
class AnalogueEvidence:
    analogue_n: int
    analogue_n_losses: int
    win_probability: float | None
    avg_win: float | None
    avg_loss: float | None
    expectancy: float | None
    profit_factor: float | None
    payoff_ratio: float | None
    tail_loss: float | None
    wins_erased_by_average_loss: float | None
    mean_lower_95: float | None
    uncertainty: str
    eligible: bool
    similarity_score: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _similarity(query: Mapping[str, str], row: Mapping[str, str]) -> float:
    keys = ("symbol", "side", "regime", "structure", "volatility", "session", "h1_direction", "m5_direction")
    hits = 0
    for key in keys:
        q = str(query.get(key, ""))
        r = str(row.get(key, ""))
        if key == "symbol":
            if q.upper() == r.upper():
                hits += 1
        elif q == r:
            hits += 1
    setup_match = 1.0 if str(query.get("setup")) == str(row.get("setup")) else 0.0
    return (hits + setup_match) / (len(keys) + 1)


def _lower_bound(values: Sequence[float]) -> float | None:
    items = [float(v) for v in values]
    if len(items) < 2:
        return None
    avg = mean(items)
    sigma = pstdev(items)
    return avg - 1.96 * (sigma / math.sqrt(len(items)))


class AnalogueStore:
    def __init__(self, records: Sequence[Mapping[str, Any]] | None = None) -> None:
        self._records = list(records or [])

    @classmethod
    def load(cls, path: Path | None = None) -> "AnalogueStore":
        target = Path(path) if path is not None else DEFAULT_ANALOGUE_PATH
        if not target.is_file():
            return cls([])
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls([])
        rows = payload.get("records") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return cls([])
        return cls([row for row in rows if isinstance(row, dict)])

    def query(
        self,
        *,
        signature: Mapping[str, str],
        before_time: str | pd.Timestamp,
        min_n: int = 20,
        min_similarity: float = 0.55,
    ) -> AnalogueEvidence:
        cutoff = pd.Timestamp(before_time)
        if cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize("UTC")
        else:
            cutoff = cutoff.tz_convert("UTC")
        matched: list[tuple[float, float]] = []
        symbol = str(signature.get("symbol") or "").upper()
        for row in self._records:
            if symbol and str(row.get("symbol") or "").upper() != symbol:
                continue
            try:
                ts = pd.Timestamp(row["bar_time"])
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                else:
                    ts = ts.tz_convert("UTC")
            except (KeyError, TypeError, ValueError):
                continue
            if ts >= cutoff:
                continue
            sim = _similarity(signature, row)
            if sim < min_similarity:
                continue
            try:
                matched.append((sim, float(row["outcome"])))
            except (KeyError, TypeError, ValueError):
                continue
        if not matched:
            return AnalogueEvidence(0, 0, None, None, None, None, None, None, None, None, None, "no_observations", False, 0.0)
        matched.sort(key=lambda item: item[0], reverse=True)
        outcomes = [value for _, value in matched]
        stats = payoff_metrics(outcomes)
        lower = _lower_bound(outcomes)
        eligible = (
            int(stats["n"]) >= min_n
            and stats.get("expectancy") is not None
            and float(stats["expectancy"]) > 0
            and lower is not None
            and lower > 0
            and not bool(stats.get("cosmetic_win_rate"))
        )
        uncertainty = (
            "insufficient_sample"
            if int(stats["n"]) < min_n
            else "mean_not_positive_with_95_confidence"
            if not eligible
            else "calibrated"
        )
        return AnalogueEvidence(
            int(stats["n"]),
            int(stats["n_losses"]),
            stats.get("win_rate"),
            stats.get("avg_win"),
            stats.get("avg_loss"),
            stats.get("expectancy"),
            stats.get("profit_factor"),
            stats.get("payoff_ratio"),
            stats.get("tail_loss"),
            stats.get("wins_erased_by_average_loss"),
            lower,
            uncertainty,
            eligible,
            float(matched[0][0]),
        )
