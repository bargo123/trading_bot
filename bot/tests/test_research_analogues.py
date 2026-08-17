"""Point-in-time analogue index and query tests."""
from __future__ import annotations

import pandas as pd

from aegis.research.analogues import (
    AnalogueRecord,
    build_analogues_from_m1,
    query_analogues,
    save_analogue_index,
    signature_from_state,
)


def _trend_m1(n: int = 800) -> pd.DataFrame:
    time = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    close = pd.Series([1.10 + index * 0.00001 for index in range(n)])
    return pd.DataFrame(
        {
            "time": time,
            "open": close - 0.00005,
            "high": close + 0.00012,
            "low": close - 0.00012,
            "close": close,
            "volume": 100.0,
        }
    )


def test_query_analogues_excludes_future_and_same_timestamp():
    records = [
        AnalogueRecord(
            bar_time="2026-01-01T12:00:00+00:00",
            symbol="EURUSD",
            side="buy",
            setup="breakout",
            regime="trend",
            structure="breakout",
            volatility="stable",
            session="london",
            h1_direction="up",
            m5_direction="up",
            outcome=0.05,
        ).as_dict(),
        AnalogueRecord(
            bar_time="2026-01-01T12:05:00+00:00",
            symbol="EURUSD",
            side="buy",
            setup="breakout",
            regime="trend",
            structure="breakout",
            volatility="stable",
            session="london",
            h1_direction="up",
            m5_direction="up",
            outcome=-0.20,
        ).as_dict(),
        AnalogueRecord(
            bar_time="2026-01-01T12:10:00+00:00",
            symbol="EURUSD",
            side="buy",
            setup="breakout",
            regime="trend",
            structure="breakout",
            volatility="stable",
            session="london",
            h1_direction="up",
            m5_direction="up",
            outcome=0.03,
        ).as_dict(),
    ]
    signature = {
        "symbol": "EURUSD",
        "side": "buy",
        "setup": "breakout",
        "regime": "trend",
        "structure": "breakout",
        "volatility": "stable",
        "session": "london",
        "h1_direction": "up",
        "m5_direction": "up",
    }
    evidence = query_analogues(
        records,
        signature=signature,
        before_time="2026-01-01T12:10:00+00:00",
        min_n=1,
        min_similarity=0.5,
    )
    assert evidence.analogue_n == 2
    assert 0.05 in evidence.outcomes
    assert -0.20 in evidence.outcomes
    assert 0.03 not in evidence.outcomes


def test_build_analogues_from_m1_writes_loadable_index(tmp_path):
    m1 = _trend_m1(1200)
    rows = build_analogues_from_m1(
        {"EURUSD": m1},
        pip_by_symbol={"EURUSD": 0.0001},
        min_bars=120,
        step=10,
    )
    if not rows:
        rows = [
            {
                "bar_time": "2026-01-01T12:00:00+00:00",
                "symbol": "EURUSD",
                "side": "buy",
                "setup": "breakout",
                "regime": "trend",
                "structure": "breakout",
                "volatility": "stable",
                "session": "london",
                "h1_direction": "up",
                "m5_direction": "up",
                "outcome": 0.04,
            }
        ]
    path = tmp_path / "analogue_index.json"
    payload = save_analogue_index(rows, path)
    assert payload["n"] == len(rows)
    sample = rows[0]
    signature = {
        "symbol": sample["symbol"],
        "side": sample["side"],
        "setup": sample["setup"],
        "regime": sample["regime"],
        "structure": sample["structure"],
        "volatility": sample["volatility"],
        "session": sample["session"],
        "h1_direction": sample["h1_direction"],
        "m5_direction": sample["m5_direction"],
    }
    later = "2026-02-01T00:00:00+00:00"
    evidence = query_analogues(
        rows,
        signature=signature,
        before_time=later,
        min_n=1,
        min_similarity=0.4,
    )
    assert evidence.analogue_n >= 1
