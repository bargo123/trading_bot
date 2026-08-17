"""Stable fingerprints for configs and OHLCV frames. No fabricated data."""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd


def _canon(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _canon(obj[k]) for k in sorted(obj, key=str)}
    if isinstance(obj, (list, tuple)):
        return [_canon(x) for x in obj]
    if isinstance(obj, float):
        return round(obj, 12)
    return obj


def config_fingerprint(cfg: dict[str, Any]) -> str:
    blob = json.dumps(_canon(cfg), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def dataset_fingerprint(df: pd.DataFrame) -> str:
    cols = [c for c in ("time", "open", "high", "low", "close", "volume") if c in df.columns]
    if not cols:
        raise ValueError("dataset fingerprint needs OHLC columns")
    sub = df.loc[:, cols].copy()
    if "time" in sub.columns:
        sub["time"] = pd.to_datetime(sub["time"], utc=True).astype("int64")
    payload = sub.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
