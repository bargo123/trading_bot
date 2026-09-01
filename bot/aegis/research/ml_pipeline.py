"""ML research pipeline: state features -> ridge regression -> OOS -> charts.

Runs on the measured mt5_m1 analogue index. Features are the point-in-time state
fields (regime, structure, volatility, session, h1/m5 direction, side, symbol).
A ridge model is trained on the earlier 70% of records (by bar_time) and scored
on the untouched last 30%. Charts are dependency-free SVG (no matplotlib) and the
raw series are exported as JSON. Research-only; never trades.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from aegis.intel.expected_value import payoff_metrics
from aegis.research.evaluate import untouched_holdout

FEATURE_FIELDS = ("regime", "structure", "volatility", "session", "h1_direction", "m5_direction")
# Numeric passthrough features appended to the design matrix (audited fix 1:
# the model was categorical-only and could not learn any numeric edge).
NUMERIC_FEATURES: tuple[str, ...] = ()
SIDE_VALUES = ("buy", "sell")
RIDGE_DEFAULT = 1.0


def feature_frame(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    for record in records:
        rows.append(
            {
                "bar_time": str(record.get("bar_time") or ""),
                "symbol": str(record.get("symbol") or "?"),
                "side": str(record.get("side") or "?"),
                "regime": str(record.get("regime") or "?"),
                "structure": str(record.get("structure") or "?"),
                "volatility": str(record.get("volatility") or "?"),
                "session": str(record.get("session") or "?"),
                "h1_direction": str(record.get("h1_direction") or "?"),
                "m5_direction": str(record.get("m5_direction") or "?"),
                "outcome": float(record["outcome"]),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("feature_frame needs at least one record")
    df = df.sort_values("bar_time").reset_index(drop=True)
    df["hour_utc"] = pd.to_datetime(df["bar_time"], utc=True).dt.hour.astype(float)
    return df


def _design_matrix(df: pd.DataFrame, train: pd.DataFrame) -> np.ndarray:
    cats = {field: sorted(train[field].astype(str).unique()) for field in FEATURE_FIELDS}
    symbols = sorted(train["symbol"].astype(str).unique())
    base_cols = [f"{field}={value}" for field in FEATURE_FIELDS for value in cats[field]]
    base_cols += ["hour_utc", "side_sell"]
    numeric = [f for f in NUMERIC_FEATURES if f in df.columns]
    base_cols += [f"num={f}" for f in numeric]
    cols = base_cols + [f"sym={symbol}" for symbol in symbols]

    matrix = np.zeros((len(df), len(cols)), dtype=float)
    for i, row in df.iterrows():
        for field in FEATURE_FIELDS:
            value = str(row[field])
            if value in cats[field]:
                matrix[i, base_cols.index(f"{field}={value}")] = 1.0
        matrix[i, base_cols.index("hour_utc")] = float(row.get("hour_utc") or 0.0)
        matrix[i, base_cols.index("side_sell")] = 1.0 if str(row["side"]) == "sell" else 0.0
        for j, f in enumerate(numeric):
            try:
                matrix[i, len(base_cols) - len(numeric) + j] = float(row.get(f) or 0.0)
            except (TypeError, ValueError):
                pass
        symbol = str(row["symbol"])
        if symbol in symbols:
            matrix[i, cols.index(f"sym={symbol}")] = 1.0
    return matrix


def ridge_fit(x: np.ndarray, y: np.ndarray, ridge: float = RIDGE_DEFAULT) -> np.ndarray:
    n = x.shape[1] + 1
    xb = np.hstack([np.ones((x.shape[0], 1)), x])
    xtx = xb.T @ xb
    reg = float(ridge) * np.eye(n)
    reg[0, 0] = 0.0
    return np.linalg.pinv(xtx + reg) @ xb.T @ y


def ridge_predict(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    xb = np.hstack([np.ones((x.shape[0], 1)), x])
    return xb @ weights


def train_and_score(
    df: pd.DataFrame,
    *,
    holdout_frac: float = 0.3,
    ridge: float = RIDGE_DEFAULT,
    take_fraction: float = 0.5,
) -> dict[str, Any]:
    train, hold = untouched_holdout(df, holdout_frac=holdout_frac)
    if train.empty or hold.empty:
        raise ValueError("empty train or holdout after time split")
    x_train = _design_matrix(train, train)
    x_hold = _design_matrix(hold, train)
    mu = x_train.mean(axis=0)
    sd = x_train.std(axis=0)
    sd = np.where(sd < 1e-12, 1.0, sd)
    x_train = (x_train - mu) / sd
    x_hold = (x_hold - mu) / sd
    y_train = train["outcome"].to_numpy(dtype=float)
    y_hold = hold["outcome"].to_numpy(dtype=float)

    weights = ridge_fit(x_train, y_train, ridge)
    pred = ridge_predict(x_hold, weights)

    order = np.argsort(pred)[::-1]
    k = max(1, int(len(pred) * take_fraction))
    take_idx = order[:k]
    taken = y_hold[take_idx]

    all_metrics = payoff_metrics(y_hold.tolist())
    taken_metrics = payoff_metrics(taken.tolist())

    return {
        "holdout_n": int(len(y_hold)),
        "train_n": int(len(y_train)),
        "take_fraction": float(take_fraction),
        "n_taken": int(len(taken)),
        "all_holdout": all_metrics,
        "model_taken": taken_metrics,
        "improvement_expectancy": (
            (taken_metrics.get("expectancy") or 0.0) - (all_metrics.get("expectancy") or 0.0)
        ),
        "equity_curve": [float(x) for x in np.cumsum(y_hold)],
        "drawdown": [float(x) for x in _drawdown_series(np.cumsum(y_hold))],
        "model_equity_curve": [float(x) for x in np.cumsum(taken)],
    }


def _drawdown_series(equity: np.ndarray) -> np.ndarray:
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    return dd


def equity_curve_svg(
    series: Sequence[float],
    *,
    width: int = 720,
    height: int = 240,
    color: str = "#2f7ed8",
    title: str = "Equity curve",
) -> str:
    values = [float(v) for v in series]
    if not values:
        return f"<svg width=\"{width}\" height=\"{height}\" xmlns=\"http://www.w3.org/2000/svg\"><text x=\"8\" y=\"20\" font-size=\"12\">{title}: no data</text></svg>"
    pad = 8
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pts = []
    for i, value in enumerate(values):
        x = pad + i * (width - 2 * pad) / max(1, len(values) - 1)
        y = height - pad - (value - lo) / span * (height - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    path = "M " + " L ".join(pts)
    zero_y = height - pad - (0 - lo) / span * (height - 2 * pad)
    return (
        f"<svg width=\"{width}\" height=\"{height}\" xmlns=\"http://www.w3.org/2000/svg\">"
        f"<line x1=\"0\" y1=\"{zero_y:.1f}\" x2=\"{width}\" y2=\"{zero_y:.1f}\" stroke=\"#999\" stroke-width=\"1\" stroke-dasharray=\"4,3\"/>"
        f"<path d=\"{path}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2\"/>"
        f"<text x=\"8\" y=\"16\" font-size=\"12\" fill=\"#333\">{title}</text></svg>"
    )


def drawdown_svg(
    series: Sequence[float],
    *,
    width: int = 720,
    height: int = 160,
    color: str = "#c0392b",
    title: str = "Drawdown",
) -> str:
    values = [float(v) for v in series]
    if not values:
        return f"<svg width=\"{width}\" height=\"{height}\" xmlns=\"http://www.w3.org/2000/svg\"><text x=\"8\" y=\"20\" font-size=\"12\">{title}: no data</text></svg>"
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pts = []
    for i, value in enumerate(values):
        x = 8 + i * (width - 16) / max(1, len(values) - 1)
        y = height - 8 - (value - lo) / span * (height - 16)
        pts.append(f"{x:.1f},{y:.1f}")
    path = "M " + " L ".join(pts)
    return (
        f"<svg width=\"{width}\" height=\"{height}\" xmlns=\"http://www.w3.org/2000/svg\">"
        f"<path d=\"{path}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2\"/>"
        f"<text x=\"8\" y=\"16\" font-size=\"12\" fill=\"#333\">{title}</text></svg>"
    )