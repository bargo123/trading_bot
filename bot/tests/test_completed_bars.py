"""Completed MT5 M1 bars must aggregate identically in research and runtime."""
from __future__ import annotations

import pandas as pd
import pytest

from aegis.intel.state_runtime import _resample as runtime_resample
from aegis.research.dataplane import resample_completed


def _numbered_m1(count: int) -> pd.DataFrame:
    minutes = pd.date_range("2026-01-01T00:00:00Z", periods=count, freq="min")
    values = pd.Series(range(count), dtype=float)
    return pd.DataFrame(
        {
            "time": minutes,
            "open": values,
            "high": values + 0.75,
            "low": values - 0.25,
            "close": values + 0.5,
            "volume": values + 1.0,
        }
    )


@pytest.mark.parametrize(("timeframe", "minutes"), (("M5", 5), ("M15", 15), ("H1", 60)))
def test_runtime_and_research_resample_identical_completed_mt5_m1(
    timeframe: str, minutes: int
) -> None:
    """MT5 M1 open timestamps define the same completed period in both consumers."""
    m1 = _numbered_m1(minutes * 2 + 1)

    research = resample_completed(m1, timeframe)[
        ["time", "open", "high", "low", "close", "volume"]
    ].reset_index(drop=True)
    runtime = runtime_resample(m1, minutes).reset_index(drop=True)

    pd.testing.assert_frame_equal(runtime, research)
