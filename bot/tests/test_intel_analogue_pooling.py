#!/usr/bin/env python3
"""Cross-symbol evidence pooling.

A state measured across 26 correlated FX pairs has a large pooled sample but a thin
per-symbol one. Hard-filtering by symbol turns a statistically supported edge into
an ineligible one, so pooling has to be possible - while still preferring
same-symbol analogues and still refusing to leak future observations.
"""
from __future__ import annotations

import pandas as pd
import pytest

from aegis.intel.analogue_store import AnalogueStore

CUTOFF = "2026-02-01T00:00:00+00:00"

STATE = {
    "side": "sell",
    "setup": "none",
    "regime": "range",
    "structure": "none",
    "volatility": "stable",
    "session": "asia",
    "h1_direction": "down",
    "m5_direction": "down",
}


def _records(symbols: list[str], per_symbol: int, *, wins_per_loss: int = 2) -> list[dict]:
    rows = []
    for symbol in symbols:
        for index in range(per_symbol):
            rows.append(
                {
                    "bar_time": f"2026-01-{(index % 27) + 1:02d}T{index % 24:02d}:00:00+00:00",
                    "symbol": symbol,
                    **STATE,
                    # +2 / -1 pips: positive expectancy with a real loss tail.
                    "outcome": -1.0 if index % (wins_per_loss + 1) == 0 else 2.0,
                }
            )
    return rows


def _store(rows: list[dict]) -> AnalogueStore:
    return AnalogueStore(rows, provenance="mt5_m1", outcome_unit="pips")


def _query(store: AnalogueStore, **kwargs):
    return store.query(
        signature={"symbol": "EURUSD", **STATE},
        before_time=CUTOFF,
        min_n=20,
        min_similarity=0.5,
        **kwargs,
    )


def test_thin_per_symbol_sample_is_ineligible_but_pooled_sample_is_not():
    """The exact reason the two real Asia-sell edges were invisible at runtime."""
    rows = _records([f"PAIR{i}" for i in range(25)] + ["EURUSD"], per_symbol=12)

    isolated = _query(_store(rows))
    pooled = _query(_store(rows), pool_across_symbols=True)

    # 12 observations for EURUSD alone: below the 20 minimum.
    assert isolated.analogue_n == 12
    assert isolated.eligible is False
    assert isolated.uncertainty == "insufficient_sample"

    # 26 symbols x 12 = 312 pooled observations of the same state.
    assert pooled.analogue_n == 312
    assert pooled.eligible is True
    assert pooled.uncertainty == "calibrated"
    assert pooled.expectancy is not None and pooled.expectancy > 0
    assert pooled.mean_lower_95 is not None and pooled.mean_lower_95 > 0


def test_pooling_is_off_by_default():
    rows = _records(["EURUSD", "GBPUSD"], per_symbol=30)
    assert _query(_store(rows)).analogue_n == 30
    assert _query(_store(rows), pool_across_symbols=True).analogue_n == 60


def test_pooling_still_ranks_same_symbol_analogues_first():
    """Symbol stays in the similarity score; it just stops being a hard filter."""
    rows = _records(["EURUSD"], per_symbol=25) + _records(["GBPUSD"], per_symbol=25)
    pooled = _query(_store(rows), pool_across_symbols=True)
    # Same-symbol rows match on every key including symbol -> perfect similarity.
    assert pooled.similarity_score == pytest.approx(1.0)


def test_pooling_does_not_leak_future_observations():
    past = _records(["GBPUSD"], per_symbol=30)
    future = [{**row, "bar_time": "2026-03-01T00:00:00+00:00"} for row in _records(["AUDUSD"], per_symbol=30)]
    pooled = _query(_store(past + future), pool_across_symbols=True)
    assert pooled.analogue_n == 30, "future-dated analogues must be excluded"


def test_pooling_cannot_rescue_a_negative_state():
    """Pooling widens the sample; it must not invent an edge."""
    rows = []
    for symbol in ("EURUSD", "GBPUSD", "AUDUSD"):
        for index in range(40):
            rows.append(
                {
                    "bar_time": f"2026-01-{(index % 27) + 1:02d}T00:00:00+00:00",
                    "symbol": symbol,
                    **STATE,
                    "outcome": 1.0 if index % 3 else -4.0,
                }
            )
    pooled = _query(_store(rows), pool_across_symbols=True)
    assert pooled.analogue_n == 120
    assert pooled.expectancy is not None and pooled.expectancy < 0
    assert pooled.eligible is False


def test_pooled_evidence_keeps_measured_provenance():
    rows = _records(["EURUSD", "GBPUSD"], per_symbol=30)
    pooled = _query(_store(rows), pool_across_symbols=True)
    assert pooled.provenance == "mt5_m1"
    assert pooled.outcome_unit == "pips"
