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
    # Provenance of the records behind this evidence. A synthetic/proxy index must
    # never be mistaken for measured market history when authorising a trade.
    provenance: str = "unknown"
    outcome_unit: str = "unknown"

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


#: Provenance labels that describe fabricated or placeholder evidence rather than
#: measured market history. ``research_proxy`` is the historical label written by
#: ``save_analogue_index`` for both synthetic and real builds, so it cannot be
#: trusted as real either.
SYNTHETIC_PROVENANCE = frozenset({"synthetic_proxy", "research_proxy", "synthetic_fixture", "unknown"})


def is_measured_provenance(provenance: str | None) -> bool:
    """True only for evidence built from real market history."""
    return str(provenance or "unknown") not in SYNTHETIC_PROVENANCE


class AnalogueStore:
    def __init__(
        self,
        records: Sequence[Mapping[str, Any]] | None = None,
        *,
        provenance: str = "unknown",
        outcome_unit: str = "unknown",
    ) -> None:
        self._records = list(records or [])
        self.provenance = str(provenance or "unknown")
        self.outcome_unit = str(outcome_unit or "unknown")

    @property
    def is_measured(self) -> bool:
        return is_measured_provenance(self.provenance)

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
        provenance = "unknown"
        outcome_unit = "unknown"
        if isinstance(payload, dict):
            provenance = str(payload.get("provenance") or payload.get("label") or "unknown")
            outcome_unit = str(payload.get("outcome_unit") or "unknown")
        return cls(
            [row for row in rows if isinstance(row, dict)],
            provenance=provenance,
            outcome_unit=outcome_unit,
        )

    def query(
        self,
        *,
        signature: Mapping[str, str],
        before_time: str | pd.Timestamp,
        min_n: int = 20,
        min_similarity: float = 0.55,
        pool_across_symbols: bool = False,
        exact_state: Mapping[str, str] | None = None,
    ) -> AnalogueEvidence:
        """Point-in-time analogue evidence for one state.

        ``pool_across_symbols`` controls whether evidence is restricted to the query
        symbol. Restricting it fragments a state's sample across 26 correlated FX
        pairs - a state with 759 pooled observations becomes ~30 per symbol and stops
        clearing the 95% lower-bound test, so a real edge becomes invisible. Pooling
        keeps symbol in the similarity score, so same-symbol analogues still rank
        first; it only stops discarding the rest outright.

        ``exact_state`` switches the match to the research validation definition: a
        record counts only if every state key (regime, structure, session, side)
        equals the query exactly, pooled across symbols. The fuzzy 9-key similarity
        pool mixes in records that differ on the state keys and can drown a small
        validated edge, so a gated brain must evaluate the same population the
        research pipeline validated.
        """
        cutoff = pd.Timestamp(before_time)
        if cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize("UTC")
        else:
            cutoff = cutoff.tz_convert("UTC")
        matched: list[tuple[float, float]] = []
        symbol = str(signature.get("symbol") or "").upper()
        exact = dict(exact_state or {})
        for row in self._records:
            if not exact:
                if symbol and not pool_across_symbols and str(row.get("symbol") or "").upper() != symbol:
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
            if exact:
                if not all(str(row.get(key) or "") == value for key, value in exact.items()):
                    continue
                sim = 1.0
            else:
                sim = _similarity(signature, row)
                if sim < min_similarity:
                    continue
            try:
                matched.append((sim, float(row["outcome"])))
            except (KeyError, TypeError, ValueError):
                continue
        if not matched:
            return AnalogueEvidence(
                0, 0, None, None, None, None, None, None, None, None, None,
                "no_observations", False, 0.0,
                provenance=self.provenance, outcome_unit=self.outcome_unit,
            )
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
            provenance=self.provenance,
            outcome_unit=self.outcome_unit,
        )
