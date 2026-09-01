"""Labeled clips from the live journal. Entry features only; flatten PnL is the label."""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import pandas as pd

from aegis.research.costs import _read_jsonl


FORBIDDEN_FEATURE_KEYS = frozenset(
    {
        "pnl",
        "held_s",
        "equity",
        "mfe",
        "mae",
        "flatten_reason",
        "exit_time",
        "snapshot_ts",
        "next_close",
        "future_close",
        "unrealized_pnl",
    }
)


class LookaheadError(ValueError):
    """A feature is only known after the trade outcome."""


def assert_no_lookahead(features: dict[str, Any]) -> None:
    leaked = sorted(k for k in features if k in FORBIDDEN_FEATURE_KEYS)
    if leaked:
        raise LookaheadError(f"lookahead feature(s): {leaked}")


def _num(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    val = row.get(key)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _entry_features(order: dict[str, Any]) -> dict[str, float]:
    bar = pd.Timestamp(order.get("bar") or order.get("ts") or "1970-01-01T00:00:00+00:00")
    if bar.tzinfo is None:
        bar = bar.tz_localize("UTC")
    else:
        bar = bar.tz_convert("UTC")
    side = str(order.get("side") or "")
    sl = _num(order, "sl")
    tp = _num(order, "tp")
    feats = {
        "spread": _num(order, "spread"),
        "qty": _num(order, "qty", 0.01),
        "side_buy": 1.0 if side == "buy" else 0.0,
        "hour_utc": float(bar.hour),
        "dow_utc": float(bar.dayofweek),
        "intel_quality": _num(order, "intel_quality"),
        "quote_age_s": _num(order, "quote_age_s"),
        "t2t_ms": _num(order, "t2t_ms"),
        "stop_tp_span": abs(tp - sl),
        "reason_up": 1.0 if "up" in str(order.get("reason") or "") else 0.0,
        "session_london": 1.0 if 7 <= bar.hour < 13 else 0.0,
        "session_ny": 1.0 if 13 <= bar.hour < 21 else 0.0,
        "spread_x_hour": _num(order, "spread") * float(bar.hour),
    }
    assert_no_lookahead(feats)
    return feats


def clips_from_journal(path: Path) -> list[dict[str, Any]]:
    """FIFO-pair successful orders with later successful flattens per symbol."""
    pending: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    clips: list[dict[str, Any]] = []
    for row in _read_jsonl(Path(path)):
        event = str(row.get("event") or "")
        symbol = str(row.get("symbol") or "")
        if event == "order" and row.get("ok") and symbol:
            pending[symbol].append(row)
            continue
        if event == "flatten" and row.get("ok") and symbol and pending[symbol]:
            order = pending[symbol].popleft()
            bar = pd.Timestamp(order.get("bar") or order.get("ts") or "1970-01-01T00:00:00+00:00")
            if bar.tzinfo is None:
                bar = bar.tz_localize("UTC")
            else:
                bar = bar.tz_convert("UTC")
            try:
                pnl = float(row.get("pnl"))
            except (TypeError, ValueError):
                continue
            feats = _entry_features(order)
            clips.append(
                {
                    "symbol": symbol,
                    "side": str(order.get("side") or ""),
                    "bar": bar,
                    "pnl": pnl,
                    "features": feats,
                }
            )
    return clips
