"""Research and runtime must describe the same completed M1 history identically."""
from __future__ import annotations

import pandas as pd

from aegis.intel.state_runtime import build_runtime_state, runtime_signature
from aegis.research.analogues import signature_from_state
from aegis.research.market_state import build_market_state


def _completed_m1(count: int = 420) -> pd.DataFrame:
    time = pd.date_range("2026-01-01T00:00:00Z", periods=count, freq="min")
    close = pd.Series([1.1000 + index * 0.00001 for index in range(count)])
    return pd.DataFrame(
        {
            "time": time,
            "open": close - 0.00003,
            "high": close + 0.00008,
            "low": close - 0.00009,
            "close": close,
            "volume": 100.0,
        }
    )


def test_runtime_and_research_state_signature_match_for_completed_m1() -> None:
    m1 = _completed_m1()
    runtime = build_runtime_state(symbol="EURUSD", m1=m1)
    research = build_market_state(symbol="EURUSD", m1=m1).as_dict()

    assert runtime["regime"]["label"] == research["regime"]["label"]
    assert runtime["structure"]["M15"]["kind"] == research["structure"]["M15"]["kind"]
    assert runtime["structure"]["M15"]["direction"] == research["multi_timeframe"]["M15"]["direction"]
    assert runtime["structure"]["M5"]["direction"] == research["multi_timeframe"]["M5"]["direction"]
    assert runtime["multi_timeframe"]["H1"]["direction"] == research["multi_timeframe"]["H1"]["direction"]
    assert runtime["session"] == research["session"]
    assert runtime_signature(runtime, side="buy", setup="scan") == {
        "symbol": "EURUSD",
        **signature_from_state(research, side="buy", setup="scan"),
    }
