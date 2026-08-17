"""Point-in-time historical analogues and sealed challenger validation."""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from aegis.research.costs import pnl_summary
from aegis.research.evaluate import combinatorial_purged_folds, purged_holdout
from aegis.research.gates import GateReject
from aegis.research.govern import governed_accept
from aegis.research.market_state import MarketState


def current_state_signature(state: MarketState, side: str) -> dict[str, Any]:
    """Small observable signature shared with historical signal-bar snapshots."""
    return {
        "side": str(side).lower(),
        "regime": str(state.regime.get("label") or "unknown"),
        "h1_direction": str((state.multi_timeframe.get("H1") or {}).get("direction") or "unavailable"),
        "m5_direction": str((state.multi_timeframe.get("M5") or {}).get("direction") or "unavailable"),
        "volatility": str(state.volatility.get("phase") or "unavailable"),
    }


def trade_state_records(trades: pd.DataFrame) -> pd.DataFrame:
    """Project backtest trades to entry-time state; outcomes remain labels."""
    rows: list[dict[str, Any]] = []
    if trades is None or trades.empty:
        return pd.DataFrame()
    for _, trade in trades.iterrows():
        snap = trade.get("intel_snap")
        if not isinstance(snap, Mapping):
            continue
        h1 = snap.get("h1_up")
        m5 = snap.get("m5_up")
        try:
            h1_direction = "up" if float(h1) >= 0.5 else "down"
            m5_direction = "up" if float(m5) >= 0.5 else "down"
        except (TypeError, ValueError):
            h1_direction = m5_direction = "unavailable"
        regime = (
            "trend"
            if h1_direction != "unavailable" and h1_direction == m5_direction
            else "range"
            if h1_direction != "unavailable" and m5_direction != "unavailable"
            else "unknown"
        )
        volatility = "expanding" if bool(snap.get("atr_expand")) else "not_expanding"
        try:
            outcome = float(trade.get("r"))
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "time": pd.Timestamp(trade.get("entry_time"), tz="UTC")
                if pd.Timestamp(trade.get("entry_time")).tzinfo is None
                else pd.Timestamp(trade.get("entry_time")).tz_convert("UTC"),
                "symbol": str(trade.get("symbol") or ""),
                "side": str(trade.get("side") or "").lower(),
                "regime": regime,
                "h1_direction": h1_direction,
                "m5_direction": m5_direction,
                "volatility": volatility,
                "outcome": outcome,
            }
        )
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True) if rows else pd.DataFrame()


def match_historical_states(records: pd.DataFrame, signature: Mapping[str, Any]) -> pd.DataFrame:
    """Match only dimensions represented identically at historical decision time."""
    if records.empty:
        return records.copy()
    mask = (
        records["side"].eq(str(signature["side"]))
        & records["regime"].eq(str(signature["regime"]))
        & records["h1_direction"].eq(str(signature["h1_direction"]))
        & records["m5_direction"].eq(str(signature["m5_direction"]))
    )
    current_vol = str(signature.get("volatility") or "")
    if current_vol == "expanding":
        mask &= records["volatility"].eq("expanding")
    elif current_vol in {"compressing", "stable"}:
        mask &= records["volatility"].eq("not_expanding")
    return records.loc[mask].reset_index(drop=True)


def _summary(frame: pd.DataFrame) -> dict[str, Any]:
    stats = pnl_summary(frame["outcome"].astype(float).tolist() if not frame.empty else [])
    return {
        "n_trades": stats["n"],
        "expectancy": stats["expectancy"],
        "profit_factor": stats["profit_factor"],
        "net_pnl": stats["net_pnl"],
        "win_rate": stats["win_rate"],
    }


def validate_state_matched_challengers(
    candidates: Mapping[str, pd.DataFrame],
    *,
    signature: Mapping[str, Any],
    min_train: int = 20,
) -> dict[str, Any]:
    """Select on purged train only, then judge once on the sealed final holdout."""
    prepared: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    train_rows: list[dict[str, Any]] = []
    for name, trades in candidates.items():
        matched = match_historical_states(trade_state_records(trades), signature)
        if len(matched) < 10:
            train_rows.append({"candidate": name, "matched": len(matched), "eligible": False})
            continue
        train, hold = purged_holdout(matched, holdout_frac=0.3, embargo_frac=0.02)
        prepared[name] = (train, hold)
        summary = _summary(train)
        train_rows.append(
            {
                "candidate": name,
                "matched": len(matched),
                "eligible": len(train) >= int(min_train),
                **{f"train_{key}": value for key, value in summary.items()},
            }
        )
    eligible = [row for row in train_rows if row.get("eligible")]
    if not eligible:
        return {
            "selected": None,
            "decision": "rejected",
            "reason": "no candidate has enough state-matched training outcomes",
            "signature": dict(signature),
            "train_search": train_rows,
            "sealed_holdout": None,
            "cpcv": [],
            "n_searches": len(candidates),
        }
    selected = max(
        eligible,
        key=lambda row: (
            float(row.get("train_expectancy") or float("-inf")),
            float(row.get("train_profit_factor") or 0.0),
        ),
    )["candidate"]
    train, hold = prepared[str(selected)]
    hold_summary = _summary(hold)
    pnls = hold["outcome"].astype(float).tolist()
    cpcv: list[dict[str, Any]] = []
    if len(train) >= 20:
        try:
            for fold, (_, test) in enumerate(
                combinatorial_purged_folds(train, n_groups=5, n_test_groups=1)
            ):
                cpcv.append({"fold": fold, **_summary(test)})
        except ValueError:
            cpcv = []
    decision = "accepted"
    reason = "governed sealed holdout passed"
    try:
        governed_accept(
            hold_summary,
            champion=None,
            pnls=pnls,
            n_searches=max(1, len(candidates)),
        )
    except (GateReject, ValueError) as exc:
        decision = "rejected"
        reason = str(exc)
    return {
        "selected": selected,
        "decision": decision,
        "reason": reason,
        "signature": dict(signature),
        "train_search": train_rows,
        "sealed_holdout": hold_summary,
        "sealed_outcomes": pnls,
        "train_max": None if train.empty else str(train["time"].max()),
        "holdout_min": None if hold.empty else str(hold["time"].min()),
        "cpcv": cpcv,
        "n_searches": len(candidates),
    }
