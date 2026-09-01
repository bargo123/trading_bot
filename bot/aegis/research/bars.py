"""Completed bars from ticks with an explicit timezone assumption."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aegis.research.dataplane import TF_MINUTES, annotate_bars, ticks_frame
from aegis.research.replay import m1_from_ticks

BAR_SCHEMA = "bars.v1"


class BarBuildError(ValueError):
    """Refuse bars that would hide an unmeasured timezone or lookahead."""


def bars_from_ticks(
    ticks: pd.DataFrame,
    *,
    tf: str,
    broker_tz: str | None,
    timezone_assumption: str | None,
) -> pd.DataFrame:
    if not timezone_assumption:
        raise BarBuildError("timezone_assumption is required until broker TZ is measured")
    if not broker_tz:
        raise BarBuildError("timezone_assumption is required until broker TZ is measured")
    if tf not in TF_MINUTES:
        raise BarBuildError(f"unsupported tf {tf}")
    frame = ticks_frame(ticks.to_dict("records"))
    m1 = m1_from_ticks(frame)
    if m1.empty:
        out = m1.copy()
        out.attrs["timezone_assumption"] = timezone_assumption
        out.attrs["broker_tz"] = broker_tz
        out.attrs["volume_kind"] = "broker_tick_volume_proxy"
        out.attrs["schema"] = BAR_SCHEMA
        return out
    if tf == "M1":
        bars = annotate_bars(m1)
    else:
        from aegis.research.dataplane import resample_completed

        bars = resample_completed(m1, tf)
    bars = bars.copy()
    utc_times = pd.to_datetime(bars["time"], utc=True)
    bars["broker_time"] = utc_times.dt.tz_convert(broker_tz)
    bars.attrs["timezone_assumption"] = timezone_assumption
    bars.attrs["broker_tz"] = broker_tz
    bars.attrs["volume_kind"] = "broker_tick_volume_proxy"
    bars.attrs["schema"] = BAR_SCHEMA
    return bars


def session_open_allowed(bars: pd.DataFrame) -> tuple[bool, str]:
    """Session-open strategies fail closed until TZ is measured, not assumed."""
    assumption = str(bars.attrs.get("timezone_assumption") or "")
    if assumption.startswith("measured:"):
        return True, assumption
    return False, "timezone_assumption"
