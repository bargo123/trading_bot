"""Versioned completed-bar data plane. No lookahead, no fake L2."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

import pandas as pd

from aegis.completed_bars import TF_MINUTES, resample_completed as _resample_completed
from aegis.research.capabilities import capabilities_snapshot
from aegis.research.fingerprint import dataset_fingerprint
from aegis.state_semantics import session_label

SCHEMA_VERSION = "dataplane.v1"

TICK_COLUMNS = (
    "symbol",
    "ts_utc",
    "ts_ms",
    "seq",
    "bid",
    "ask",
    "last",
    "tick_volume",
    "flags",
)


def ticks_frame(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    missing = [c for c in TICK_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"tick frame missing columns: {missing}")
    out = df.loc[:, list(TICK_COLUMNS)].copy()
    out["ts_utc"] = pd.to_datetime(out["ts_utc"], utc=True)
    out["tick_volume"] = out["tick_volume"].astype(float)
    out.attrs["volume_kind"] = "broker_tick_volume_proxy"
    return out.sort_values(["ts_utc", "seq"]).reset_index(drop=True)


def annotate_bars(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["time"] = pd.to_datetime(out["time"], utc=True)
    out["session"] = [session_label(t) for t in out["time"]]
    out["schema"] = SCHEMA_VERSION
    return out


def resample_completed(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    return annotate_bars(_resample_completed(m1, tf))


def contract_snapshot(
    *,
    symbol: str,
    digits: int,
    point: float,
    tick_value: float,
    tick_size: float | None = None,
    contract_size: float | None = None,
    volume_min: float | None = None,
    volume_max: float | None = None,
    volume_step: float | None = None,
    stops_level: float | None = None,
    freeze_level: float | None = None,
    margin_mode: str | None = None,
    depth_available: bool = False,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "symbol": symbol,
        "digits": int(digits),
        "point": float(point),
        "tick_value": float(tick_value),
        "tick_size": None if tick_size is None else float(tick_size),
        "contract_size": None if contract_size is None else float(contract_size),
        "volume_min": None if volume_min is None else float(volume_min),
        "volume_max": None if volume_max is None else float(volume_max),
        "volume_step": None if volume_step is None else float(volume_step),
        "stops_level": None if stops_level is None else float(stops_level),
        "freeze_level": None if freeze_level is None else float(freeze_level),
        "margin_mode": margin_mode,
        "depth_available": bool(depth_available),
        "l2": False,
    }


def fill_fact(
    *,
    symbol: str,
    side: str,
    request_ts: str,
    quote_ts: str,
    ack_ts: str | None,
    status: str,
    fill_price: float | None,
    spread: float | None,
    commission: float = 0.0,
    swap: float = 0.0,
    slippage: float | None = None,
    latency_ms: float | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "symbol": symbol,
        "side": side,
        "request_ts": request_ts,
        "quote_ts": quote_ts,
        "ack_ts": ack_ts,
        "status": status,
        "fill_price": fill_price,
        "spread": spread,
        "commission": float(commission),
        "swap": float(swap),
        "slippage": slippage,
        "latency_ms": latency_ms,
    }


def dataset_bundle_fingerprint(frames: dict[str, pd.DataFrame], meta: dict[str, Any]) -> str:
    parts = [json.dumps(meta, sort_keys=True, separators=(",", ":"))]
    for name in sorted(frames):
        parts.append(name)
        parts.append(dataset_fingerprint(frames[name]))
    blob = "|".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def multi_tf_bundle(m1: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {tf: resample_completed(m1, tf) for tf in TF_MINUTES}


def time_at_price(m1: pd.DataFrame, *, bins: int = 24) -> pd.DataFrame:
    """Minute occupancy by price. Broker M1 range is a proxy, not exchange TPO."""
    if m1.empty:
        return pd.DataFrame(columns=["price_mid", "minutes", "kind"])
    lo = float(m1["low"].min())
    hi = float(m1["high"].max())
    if hi <= lo:
        return pd.DataFrame([{"price_mid": lo, "minutes": len(m1), "kind": "time_at_price_proxy"}])
    edges = pd.interval_range(start=lo, end=hi, periods=bins)
    mids = []
    minutes = []
    for iv in edges:
        hits = int(((m1["low"] <= iv.right) & (m1["high"] >= iv.left)).sum())
        mids.append((float(iv.left) + float(iv.right)) / 2.0)
        minutes.append(hits)
    return pd.DataFrame({"price_mid": mids, "minutes": minutes, "kind": "time_at_price_proxy"})


__all__ = [
    "SCHEMA_VERSION",
    "TICK_COLUMNS",
    "annotate_bars",
    "capabilities_snapshot",
    "contract_snapshot",
    "dataset_bundle_fingerprint",
    "fill_fact",
    "multi_tf_bundle",
    "resample_completed",
    "session_label",
    "ticks_frame",
    "time_at_price",
]
