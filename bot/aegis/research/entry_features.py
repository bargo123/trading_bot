"""Rolling structure and higher-timeframe columns for research entries.

Everything here is computed so that the value on bar `i` depends only on bars `<= i`.
A swing high at bar `i` is not usable until bar `i+1` has closed, which is why the
pivot columns are shifted before they are carried forward. The regression test
recomputes on truncated frames and requires identical values.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RETEST_BAND = 0.0003


def add_structure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Last confirmed pivot levels and the structure event at each completed bar."""
    out = df.copy()
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    close = out["close"].astype(float)

    is_swing_high = (high > high.shift(1)) & (high >= high.shift(-1))
    is_swing_low = (low < low.shift(1)) & (low <= low.shift(-1))

    # A swing is only decided once the following bar closes, so shift by one bar
    # before carrying the level forward.
    confirmed_high = high.where(is_swing_high).shift(1)
    confirmed_low = low.where(is_swing_low).shift(1)
    out["piv_high"] = confirmed_high.ffill()
    out["piv_low"] = confirmed_low.ffill()

    res = out["piv_high"]
    sup = out["piv_low"]
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    event = pd.Series("none", index=out.index, dtype=object)
    broke_up = res.notna() & (close > res)
    broke_dn = sup.notna() & (close < sup)
    failed_up = res.notna() & (prev_high > res) & (close < res)
    failed_dn = sup.notna() & (prev_low < sup) & (close > sup)
    near_res = res.notna() & ((close - res).abs() / res.abs().clip(lower=1e-9) < RETEST_BAND)
    near_sup = sup.notna() & ((close - sup).abs() / sup.abs().clip(lower=1e-9) < RETEST_BAND)

    event = event.mask(near_sup, "retest_dn")
    event = event.mask(near_res, "retest_up")
    event = event.mask(broke_dn, "breakout_dn")
    event = event.mask(broke_up, "breakout_up")
    event = event.mask(failed_dn, "failure_dn")
    event = event.mask(failed_up, "failure_up")
    out["struct_event"] = event
    return out


def _completed_direction(out: pd.DataFrame, minutes: int) -> pd.Series:
    """1.0 when the last *completed* bar of that timeframe closed up, else 0.0."""
    times = pd.to_datetime(out["time"], utc=True)
    indexed = out.set_index(times)
    agg = indexed.resample(f"{minutes}min", label="left", closed="left").agg(
        {"open": "first", "close": "last"}
    )
    direction = (agg["close"] >= agg["open"]).astype(float)
    direction[agg["open"].isna()] = np.nan
    # The bucket covering bar i is still forming, so step back one completed bucket.
    completed = direction.shift(1)
    mapped = completed.reindex(times.dt.floor(f"{minutes}min")).to_numpy()
    return pd.Series(mapped, index=out.index, dtype=float)


def add_htf_direction(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["m5_up"] = _completed_direction(out, 5)
    out["h1_up"] = _completed_direction(out, 60)
    return out


def add_entry_features(df: pd.DataFrame) -> pd.DataFrame:
    return add_htf_direction(add_structure_columns(df))
