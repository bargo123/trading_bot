"""Independent book modules: provenance, no blended super-signal."""
from __future__ import annotations

import pandas as pd

from aegis.research.harris import spread_allows_take
from aegis.research.modules import IMPLEMENTED, collect_setups, vpa_effort_setup


def _frame(n: int = 40, *, vol: float = 100, drift: float = 0.00001) -> pd.DataFrame:
    t = pd.date_range("2026-01-05 00:00", periods=n, freq="min", tz="UTC")
    close = 1.10 + pd.Series(range(n)).astype(float) * drift
    return pd.DataFrame(
        {
            "time": t,
            "open": close - 0.00005,
            "high": close + 0.0002,
            "low": close - 0.0002,
            "close": close,
            "volume": vol,
        }
    )


def test_vpa_requires_effort_expansion():
    quiet = _frame(40)
    assert vpa_effort_setup(m5=quiet) is None
    loud = _frame(40)
    loud.loc[loud.index[-1], "volume"] = 400
    loud.loc[loud.index[-1], "high"] = float(loud["close"].iloc[-1]) + 0.001
    hit = vpa_effort_setup(m5=loud)
    assert hit is not None
    assert hit.provenance.startswith("coulling:")
    assert "exchange" not in hit.provenance


def test_collect_setups_drops_disagreement():
    m5 = _frame(20)
    h1 = _frame(4, drift=-0.001)
    # range location buy vs h1 sell should cancel
    out = collect_setups(m5=m5, h1=h1, regime="range")
    assert out == [] or len({s.side for s in out}) == 1


def test_implemented_catalog_is_explicit():
    assert IMPLEMENTED["brooks_range"].startswith("aegis.research.modules")
    assert spread_allows_take(spread_pips=0.2, take_pips=1.0)
    assert not spread_allows_take(spread_pips=1.2, take_pips=1.0)
