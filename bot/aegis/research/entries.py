"""A selective structure entry, as an alternative to the every-bar EMA firehose.

Measured finding this replaces: the live entry fires on every completed bar from the
EMA side alone, and its expectancy is negative at every stop/target ratio tested, so
no exit geometry rescues it. This entry is deliberately different in kind: it waits
for a pullback inside an established trend, puts the stop where the idea is wrong
(beyond the prior swing), and takes profit at a multiple of that risk.

Provenance is Brooks-flavoured pullback continuation with a Damir-flavoured
higher-timeframe bias. It is a `research_proxy`, not a faithful implementation of
either author, and the trend filter is a long M1 EMA rather than a true H4 series.
Every column is built from completed bars only.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from aegis.features import enrich_all
from aegis.strategy import Signal

ENTRY_NAME = "pullback_retest"
LABEL = "research_proxy"


def prepare_pullback(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Add swing and trend columns. Each is shifted so a bar never sees its own future."""
    out = enrich_all(df, cfg)
    swing = max(2, int(cfg.get("pullback_swing_bars", 20)))
    trend_n = max(20, int(cfg.get("pullback_trend_ema", 240)))
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    close = out["close"].astype(float)

    # Prior-window extremes: shift(1) keeps the current bar out of its own swing.
    out["swing_hi_prior"] = high.rolling(swing).max().shift(1)
    out["swing_lo_prior"] = low.rolling(swing).min().shift(1)
    out["trend_ema"] = close.ewm(span=trend_n, adjust=False).mean()
    out["trend_ema_prior"] = out["trend_ema"].shift(swing)
    out["trend_up"] = (close > out["trend_ema"]) & (out["trend_ema"] > out["trend_ema_prior"])
    out["trend_dn"] = (close < out["trend_ema"]) & (out["trend_ema"] < out["trend_ema_prior"])

    # Pullback: price came back to the trend EMA within the last few bars, then this
    # completed bar resumed through the prior bar's extreme. Recovery from a deep EMA
    # probe takes more than one bar, so the touch is looked for over a window rather
    # than on the immediately prior bar.
    touch_bars = max(2, int(cfg.get("pullback_touch_bars", 10)))
    atr = out["atr"].astype(float) if "atr" in out.columns else (high - low)
    tol = float(cfg.get("pullback_touch_atr", 0.5)) * atr
    touched_from_above = (low - out["trend_ema"]) <= tol
    touched_from_below = (out["trend_ema"] - high) <= tol
    recent_touch_up = (
        touched_from_above.fillna(False).rolling(touch_bars).max().shift(1).fillna(0).astype(bool)
    )
    recent_touch_dn = (
        touched_from_below.fillna(False).rolling(touch_bars).max().shift(1).fillna(0).astype(bool)
    )
    resumed_up = close > high.shift(1)
    resumed_dn = close < low.shift(1)

    out["pullback_long"] = (out["trend_up"] & recent_touch_up & resumed_up).fillna(False)
    out["pullback_short"] = (out["trend_dn"] & recent_touch_dn & resumed_dn).fillna(False)
    return out


def _pip(cfg: dict[str, Any]) -> float:
    return float(cfg.get("pullback_pip_size", cfg.get("firehose_pip_size", 0.0001)))


def sig_pullback_retest(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Long/short continuation on a completed pullback bar. Stop beyond the swing."""
    for key in ("close", "swing_hi_prior", "swing_lo_prior", "trend_ema"):
        if key not in row.index or pd.isna(row.get(key)):
            return None
    long_ok = bool(row.get("pullback_long"))
    short_ok = bool(row.get("pullback_short"))
    if not long_ok and not short_ok:
        return None

    close = float(row["close"])
    rr = float(cfg.get("pullback_rr", 2.0))
    pip = _pip(cfg)
    buffer = float(cfg.get("pullback_stop_buffer_pips", 1.0)) * pip
    min_stop = float(cfg.get("pullback_min_stop_pips", 3.0)) * pip

    if long_ok:
        stop = float(row["swing_lo_prior"]) - buffer
        if close - stop < min_stop:
            return None
        target = close + rr * (close - stop)
        return Signal("buy", ENTRY_NAME, close, stop, target, None, row["time"], "pullback_long")

    stop = float(row["swing_hi_prior"]) + buffer
    if stop - close < min_stop:
        return None
    target = close - rr * (stop - close)
    return Signal("sell", ENTRY_NAME, close, stop, target, None, row["time"], "pullback_short")


def pullback_candidate(cfg: dict[str, Any]):
    """Describe this entry in the research candidate contract."""
    from aegis.research.candidate import CandidateSpec

    rr = float(cfg.get("pullback_rr", 2.0))
    min_stop = float(cfg.get("pullback_min_stop_pips", 3.0))
    return CandidateSpec(
        name=ENTRY_NAME,
        regime="trend",
        timeframe="M1",
        data_requirements=("M1_completed_bars",),
        entry="pullback against a rising/falling long EMA, then close back through the prior bar",
        invalidation_stop="beyond the prior swing extreme plus a buffer",
        risk_percent=float(cfg.get("risk_percent", 0.25)),
        exit=f"fixed {rr}R target from the invalidation distance",
        max_hold=str(cfg.get("max_hold_bars", "none")),
        filters=("min_stop_distance", "trend_alignment"),
        tp_pips=rr * min_stop,
        sl_pips=min_stop,
        label=LABEL,
    )
