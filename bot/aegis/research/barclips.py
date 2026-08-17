"""Training clips from backtest trades, using market state at the signal bar.

The journal only recorded execution metadata, so journal clips cannot express price
context. Backtest trades carry `intel_snap`, which is captured on the completed
signal bar before the next-open fill, so those fields are known at entry. Outcome
fields (`pnl`, `r`, `mfe`, `mae`, `bars_held`, `exit_time`) are labels or
after-the-fact and never become features.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from aegis.research.dataset import assert_no_lookahead

BOOKKEEPING_KEYS = frozenset({"time", "symbol", "side", "bar", "data_source"})

# Absolute price levels differ by symbol and drift with time, so a time-ordered split
# lets a model use them as a stand-in for "which symbol / which week" instead of for
# market state. Normalized cousins (close_ema_pips, ret3_pips, rsi) stay.
PRICE_LEVEL_KEYS = frozenset({"open", "high", "low", "close", "ema_20", "htf_ema", "atr"})


def _bar_time(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def clips_from_backtest_trades(
    trades: pd.DataFrame,
    *,
    data_source: str,
) -> list[dict[str, Any]]:
    """Build time-ordered clips whose features are the signal-bar snapshot only."""
    if trades is None or len(trades) == 0:
        return []
    if "intel_snap" not in trades.columns:
        raise ValueError("trades frame has no intel_snap column")
    clips: list[dict[str, Any]] = []
    for _, row in trades.iterrows():
        snap = row.get("intel_snap")
        if not isinstance(snap, Mapping):
            continue
        assert_no_lookahead(dict(snap))
        bar = _bar_time(snap.get("time") or row.get("entry_time"))
        features: dict[str, float] = {}
        for key, value in snap.items():
            if key in BOOKKEEPING_KEYS or key in PRICE_LEVEL_KEYS:
                continue
            number = _numeric(value)
            if number is not None:
                features[str(key)] = number
        features["side_buy"] = 1.0 if str(row.get("side")) == "buy" else 0.0
        features["hour_utc"] = float(bar.hour)
        features["dow_utc"] = float(bar.dayofweek)
        assert_no_lookahead(features)
        try:
            pnl = float(row.get("pnl"))
        except (TypeError, ValueError):
            continue
        clips.append(
            {
                "symbol": str(row.get("symbol") or ""),
                "side": str(row.get("side") or ""),
                "bar": bar,
                "pnl": pnl,
                "data_source": str(data_source),
                "features": features,
            }
        )
    clips.sort(key=lambda c: c["bar"])
    return clips


def market_state_columns(clips: Sequence[Mapping[str, Any]]) -> list[str]:
    """Feature names present in every clip, sorted for a stable design matrix."""
    if not clips:
        return []
    common: set[str] | None = None
    for clip in clips:
        keys = {k for k in clip["features"]}
        common = keys if common is None else (common & keys)
    return sorted(common or set())


def clips_frame(clips: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    for clip in clips:
        row = dict(clip["features"])
        row["symbol"] = clip["symbol"]
        row["side"] = clip["side"]
        row["time"] = clip["bar"]
        row["pnl"] = clip["pnl"]
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("no bar clips to train on")
    return frame.sort_values("time").reset_index(drop=True)
