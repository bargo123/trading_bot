"""Runtime market context for Intelligent Firehose. No research imports."""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from aegis.completed_bars import TF_MINUTES, resample_completed
from aegis.state_semantics import atr, classify_regime, compression, direction, session_label, structure_event, volatility


def _structure_full(frame: pd.DataFrame) -> dict[str, Any]:
    """Complete structure with S/R, direction, ATR, compression from completed bars."""
    if frame.empty:
        return {
            "kind": "unavailable",
            "support": None,
            "resistance": None,
            "direction": "unavailable",
            "atr": None,
            "compression": None,
        }
    event = structure_event(frame)
    return {
        "kind": event["kind"],
        "support": event["support"],
        "resistance": event["resistance"],
        "direction": direction(frame),
        "atr": atr(frame),
        "compression": compression(frame.tail(1)),
    }


def _resample(m1: pd.DataFrame, minutes: int) -> pd.DataFrame:
    for timeframe, timeframe_minutes in TF_MINUTES.items():
        if timeframe_minutes == minutes:
            return resample_completed(m1, timeframe)
    raise ValueError(f"unsupported timeframe minutes: {minutes}")


def build_runtime_state(*, symbol: str, m1: pd.DataFrame) -> dict[str, Any]:
    """Minimal completed-bar state for demo brain and analogue signatures."""
    source = m1.copy()
    source["time"] = pd.to_datetime(source["time"], utc=True)
    source = source.sort_values("time").reset_index(drop=True)
    m5 = _resample(source, 5)
    m15 = _resample(source, 15)
    h1 = _resample(source, 60)
    h1_dir = direction(h1)
    m15_struct = _structure_full(m15)
    m5_struct = _structure_full(m5)
    return {
        "schema": "runtime_state.v1",
        "symbol": str(symbol).upper(),
        "observed_at": str(source["time"].iloc[-1]),
        "regime": classify_regime(source),
        "structure": {
            "M15": {
                "kind": m15_struct["kind"],
                "support": m15_struct["support"],
                "resistance": m15_struct["resistance"],
                "direction": m15_struct["direction"],
                "atr": m15_struct["atr"],
            },
            "M5": {
                "kind": m5_struct["kind"],
                "support": m5_struct["support"],
                "resistance": m5_struct["resistance"],
                "direction": m5_struct["direction"],
                "atr": m5_struct["atr"],
                "compression": m5_struct["compression"],
            },
        },
        "multi_timeframe": {
            "M5": {"direction": m5_struct["direction"]},  # genuine M5 direction from completed bars
            "M15": {"direction": m15_struct["direction"]},  # genuine M15 direction from completed bars
            "H1": {"direction": h1_dir},
        },
        "volatility": volatility(source),
        "session": session_label(source["time"].iloc[-1]),
    }


def _session(ts: pd.Timestamp) -> str:
    """Session label. Must match aegis.research.dataplane.session_label so runtime
    signatures line up with the analogue index and validated-state allowlists.
    """
    return session_label(ts)


def runtime_signature(state: Mapping[str, Any], *, side: str, setup: str) -> dict[str, str]:
    mtf = state.get("multi_timeframe") if isinstance(state.get("multi_timeframe"), Mapping) else {}
    structure = state.get("structure") if isinstance(state.get("structure"), Mapping) else {}
    m15 = structure.get("M15") if isinstance(structure.get("M15"), Mapping) else {}
    regime = state.get("regime") if isinstance(state.get("regime"), Mapping) else {}
    vol = state.get("volatility") if isinstance(state.get("volatility"), Mapping) else {}
    return {
        "symbol": str(state.get("symbol") or ""),
        "side": str(side).lower(),
        "setup": str(setup or "unknown"),
        "regime": str(regime.get("label") or "unknown"),
        "structure": str(m15.get("kind") or "none"),
        "volatility": str(vol.get("phase") or "unknown"),
        "session": str(state.get("session") or "unknown"),
        "h1_direction": str((mtf.get("H1") or {}).get("direction") or "unavailable"),
        "m5_direction": str((mtf.get("M5") or {}).get("direction") or "unavailable"),
    }
