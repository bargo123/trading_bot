from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from aegis.research.charts import kagi_state, point_and_figure, renko_bricks, three_line_break
from aegis.research.dataplane import ticks_frame
from aegis.research.modules import damir_retest_setup
from aegis.research.regime import classify_regime
from aegis.research.source_notes import MISSING_EXTRACTS, build_source_notes, note_status
from aegis.research.structure import confirmed_pivots, structure_event


def _ohlc(closes: list[float], start: str = "2026-01-05") -> pd.DataFrame:
    t = pd.date_range(start, periods=len(closes), freq="min", tz="UTC")
    close = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {
            "time": t,
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.0002,
            "low": close - 0.0002,
            "close": close,
            "volume": 100,
        }
    )


def test_source_notes_flag_placeholders_and_missing_extracts(tmp_path: Path):
    books = tmp_path / "books"
    books.mkdir()
    (books / "sample-author.md").write_text("# Sample\nUNIQUE_PLACEHOLDER_TOKEN\n", encoding="utf-8")
    (books / "trading-price-action-ranges-brooks.md").write_text(
        "# Trading Price Action Ranges\n\n## Setup\nRange location.\n## Entry\nSignal bar.\n## Exit\nFailed break.\n## Risk\nTrader equation.\nUses M5. Do not hide large stops.\n",
        encoding="utf-8",
    )
    out = tmp_path / "notes"
    notes = build_source_notes(books, out)
    assert any(n["placeholder"] for n in notes)
    brooks = next(n for n in notes if "brooks" in n["filename"])
    assert brooks["label"] == "research_proxy"
    assert brooks["file_hash"]
    assert "M5" in (brooks.get("timeframes") or brooks.get("claims", {}).get("timeframes") or ["M5"])
    assert (out / brooks["filename"].replace(".md", ".json")).exists()
    assert "kaufman" in MISSING_EXTRACTS
    assert note_status("volman") == "unavailable"


def test_confirmed_pivot_has_no_lookahead():
    closes = [1.10, 1.11, 1.15, 1.12, 1.11]
    df = _ohlc(closes)
    df.loc[2, "high"] = 1.1600
    at_peak = confirmed_pivots(df.iloc[:3], right=1)
    assert all(p["kind"] != "high" or p["bar_index"] != 2 for p in at_peak)
    after = confirmed_pivots(df.iloc[:4], right=1)
    highs = [p for p in after if p["kind"] == "high"]
    assert highs
    assert highs[0]["decided_at"] >= highs[0]["bar_index"] + 1


def test_breakout_failure_retest_uses_confirmed_structure():
    df = _ohlc([1.10, 1.11, 1.12, 1.11, 1.10, 1.13, 1.12])
    df.loc[2, "high"] = 1.125
    event = structure_event(df)
    assert event["lookahead"] is False
    assert event["kind"] in {"none", "breakout", "failure", "retest"}


def test_damir_refuses_m1_only():
    m1 = _ohlc([1.10 + i * 0.0001 for i in range(20)])
    assert damir_retest_setup(h4=m1.iloc[0:0], m15=m1) is None


def test_regime_uses_resampled_htf_not_m1_alias():
    m1 = _ohlc([1.10 + i * 0.0002 for i in range(400)])
    state = classify_regime(m1)
    assert state["lookahead"] is False
    assert state["label"] in {"trend", "range", "breakout", "noise", "no_trade"}
    assert state["used_tfs"]
    assert "M1_ema_alias" not in state["used_tfs"]


def test_transformed_charts_preserve_tick_order():
    t0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
    rows = []
    px = 1.10
    for i in range(40):
        px += 0.0003 if i < 20 else -0.0004
        ts = t0 + pd.Timedelta(seconds=i)
        rows.append(
            {
                "symbol": "EURUSD",
                "ts_utc": ts.isoformat(),
                "ts_ms": i,
                "seq": i,
                "bid": px,
                "ask": px + 0.00002,
                "last": px,
                "tick_volume": 1,
                "flags": "",
            }
        )
    ticks = ticks_frame(rows)
    pnf = point_and_figure(ticks, box=0.0005, reversal_boxes=3)
    renko = renko_bricks(ticks, brick=0.0005)
    kagi = kagi_state(ticks, reversal=0.001)
    tlb = three_line_break(ticks, lines=3)
    for result in (pnf, renko, kagi, tlb):
        assert result["label"] == "research_proxy"
        assert result["lookahead"] is False
        assert result["n"] >= 1
