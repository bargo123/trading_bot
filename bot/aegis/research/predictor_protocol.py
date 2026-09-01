"""Predictor research protocol (audit remediation 1).

TRAIN -> INNER TIME-AWARE WALK-FORWARD -> choose model/threshold ->
LOCK EVERYTHING -> ONE FINAL SEALED HOLDOUT EVALUATION.

The selection threshold is learned ONLY from inner walk-forward folds. The
final holdout is touched exactly once, with everything locked. There is no
automatic top-50% take: a candidate filter must clear the learned threshold,
and ``ml_advances`` stays false unless the sealed taken-set shows genuine
absolute positive costed expectancy (not relative improvement).
"""
from __future__ import annotations

from typing import Any

import numpy as np

try:
    from aegis.research.ml_pipeline import RIDGE_DEFAULT
except ImportError:
    RIDGE_DEFAULT = 1.0


def _pearson(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 3 or np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    return _pearson(rx, ry)


def _bootstrap_p05(values: np.ndarray, *, n_boot: int = 300, seed: int = 7) -> float | None:
    if len(values) < 5:
        return None
    rng = np.random.default_rng(seed)
    means = [
        float(np.mean(rng.choice(values, size=len(values), replace=True)))
        for _ in range(n_boot)
    ]
    return round(float(np.percentile(means, 5)), 5)


def _bucket_metrics(actual: np.ndarray, predicted_mean: float) -> dict[str, Any]:
    wins = actual[actual > 0]
    losses = actual[actual <= 0]
    gp = float(wins.sum())
    gl = abs(float(losses.sum()))
    n = len(actual)
    return {
        "n": int(n),
        "predicted_mean": round(float(predicted_mean), 5),
        "actual_ev": round(float(actual.mean()), 5) if n else None,
        "profit_factor": round(gp / gl, 4) if gl > 0 else (None if gp == 0 else 99.0),
        "win_rate": round(len(wins) / n, 4) if n else None,
        "avg_win": round(float(wins.mean()), 4) if len(wins) else None,
        "avg_loss": round(float(losses.mean()), 4) if len(losses) else None,
        "bootstrap_p05": _bootstrap_p05(actual),
    }


def _decile_report(pred: np.ndarray, actual: np.ndarray, *, buckets: int = 10) -> list[dict[str, Any]]:
    order = np.argsort(pred)
    chunks = np.array_split(order, buckets)
    out = []
    for idx in chunks:
        if len(idx) == 0:
            continue
        out.append(_bucket_metrics(actual[idx], float(pred[idx].mean())))
    return out


def _monotonicity_fraction(deciles: list[dict[str, Any]]) -> float | None:
    evs = [d["actual_ev"] for d in deciles if d["actual_ev"] is not None]
    if len(evs) < 3:
        return None
    rises = sum(1 for a, b in zip(evs, evs[1:]) if b >= a - 1e-12)
    return round(rises / (len(evs) - 1), 4)


import pandas as pd  # noqa: E402  (used above in helper)

from aegis.research.evaluate import untouched_holdout  # noqa: E402
from aegis.research.ml_pipeline import (  # noqa: E402
    RIDGE_DEFAULT,
    _design_matrix,
    _drawdown_series,
    ridge_fit,
    ridge_predict,
)


def _walk_forward_inner(
    df_inner: pd.DataFrame,
    *,
    n_folds: int,
    ridge: float,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Time-aware inner walk-forward: train strictly on data BEFORE each fold."""
    import pandas as pd

    df_inner = df_inner.sort_values("bar_time").reset_index(drop=True) \
        if "bar_time" in df_inner.columns else df_inner.reset_index(drop=True)
    folds = np.array_split(np.arange(len(df_inner)), n_folds + 1)
    preds = []
    actuals = []
    stability = []
    for k in range(1, n_folds + 1):
        train_idx = np.concatenate(folds[:k])
        test_idx = folds[k]
        tr = df_inner.iloc[train_idx].reset_index(drop=True)
        te = df_inner.iloc[test_idx].reset_index(drop=True)
        x_tr = _design_matrix(tr, tr)
        mu = x_tr.mean(axis=0)
        sd = x_tr.std(axis=0)
        sd = np.where(sd < 1e-12, 1.0, sd)
        x_tr = (x_tr - mu) / sd
        x_te = (_design_matrix(te, tr) - mu) / sd
        y_tr = tr["outcome"].to_numpy(dtype=float)
        w = ridge_fit(x_tr, y_tr, ridge)
        p = ridge_predict(x_te, w)
        y = te["outcome"].to_numpy(dtype=float)
        preds.append(p)
        actuals.append(y)
        stability.append({
            "fold": k,
            "n_test": int(len(y)),
            "fold_top_half_ev": round(float(np.mean(y[np.argsort(p)[::-1][:max(1, len(y)//2)]])), 5),
            "fold_bottom_half_ev": round(float(np.mean(y[np.argsort(p)[:max(1, len(y)//2)]])), 5),
        })
    return np.concatenate(preds), np.concatenate(actuals), stability


import pandas as pd  # noqa: E402  (used above in helper)


def choose_threshold(
    inner_pred: np.ndarray,
    inner_actual: np.ndarray,
    *,
    quantiles: tuple[float, ...] = (0.50, 0.60, 0.70, 0.80, 0.90),
    min_trades: int = 30,
) -> dict[str, Any]:
    """Pick the take-threshold ONLY from inner walk-forward predictions."""
    candidates = []
    for q in quantiles:
        thr = float(np.quantile(inner_pred, 1.0 - q))
        mask = inner_pred >= thr
        n = int(mask.sum())
        if n < min_trades:
            continue
        ev = float(inner_actual[mask].mean())
        candidates.append({"quantile": q, "threshold": round(thr, 6),
                           "n_inner": n, "inner_ev": round(ev, 5)})
    if not candidates:
        return {"threshold": None, "reason": "no_candidate_cleared_min_trades",
                "candidates": []}
    best = max(candidates, key=lambda c: c["inner_ev"])
    source = "inner_walkforward"
    note = ""
    if best["inner_ev"] <= 0:
        # No threshold gives positive inner EV: do NOT pick one for trading.
        return {"threshold": None, "source": source, "candidates": candidates,
                "reason": "no_threshold_positive_on_inner_walkforward",
                "best_inner_ev": best["inner_ev"]}
    # Monotonicity sanity inside inner data at the chosen threshold.
    mask_hi = inner_pred >= best["threshold"]
    mask_lo = ~mask_hi
    mono_ok = (inner_actual[mask_hi].mean() > inner_actual[mask_lo].mean()) \
        if mask_lo.any() else True
    if not mono_ok:
        note = "high-bucket did not beat low-bucket on inner data"
    return {"threshold": best["threshold"], "source": source,
            "quantile": best["quantile"], "inner_ev": best["inner_ev"],
            "candidates": candidates, "note": note}


def run_predictor_protocol(
    df: pd.DataFrame,
    *,
    holdout_frac: float = 0.3,
    ridge: float = RIDGE_DEFAULT,
    n_folds: int = 4,
    meta: pd.DataFrame | None = None,
    min_trades_threshold: int = 30,
) -> dict[str, Any]:
    """Full protocol. The sealed holdout is evaluated exactly once."""
    split = untouched_holdout(df, holdout_frac=holdout_frac)
    inner, sealed = split
    if inner.empty or sealed.empty:
        raise ValueError("empty inner or sealed after time split")
    inner = inner.reset_index(drop=True)
    sealed = sealed.reset_index(drop=True)

    inner_pred, inner_actual, wf_stability = _walk_forward_inner(
        inner, n_folds=n_folds, ridge=ridge)

    choice = choose_threshold(inner_pred, inner_actual,
                              min_trades=min_trades_threshold)
    threshold = choice.get("threshold")

    # LOCK model+threshold; fit on ALL inner data; single sealed evaluation.
    x_in = _design_matrix(inner, inner)
    mu = x_in.mean(axis=0)
    sd = np.where(x_in.std(axis=0) < 1e-12, 1.0, x_in.std(axis=0))
    x_in = (x_in - mu) / sd
    y_in = inner["outcome"].to_numpy(dtype=float)
    weights = ridge_fit(x_in, y_in, ridge)

    x_se = (_design_matrix(sealed, inner) - mu) / sd
    pred_se = ridge_predict(x_se, weights)
    y_se = sealed["outcome"].to_numpy(dtype=float)

    taken_mask = (pred_se >= threshold) if threshold is not None \
        else np.zeros(len(pred_se), dtype=bool)
    taken = y_se[taken_mask]

    sealed_all_metrics = {
        "expectancy": round(float(y_se.mean()), 5),
        "n": int(len(y_se)),
    }
    taken_metrics = {
        "n": int(len(taken)),
        "expectancy": round(float(taken.mean()), 5) if len(taken) else None,
        "bootstrap_p05": _bootstrap_p05(taken) if len(taken) else None,
    }
    wins = taken[taken > 0]
    losses = taken[taken <= 0]
    gp, gl = float(wins.sum()), abs(float(losses.sum()))
    taken_metrics["profit_factor"] = (
        round(gp / gl, 4) if gl > 0 else (None if gp == 0 else 99.0))

    deciles = _decile_report(pred_se, y_se)
    monotonicity = _monotonicity_fraction(deciles)

    ml_advances = bool(
        threshold is not None
        and len(taken) >= 20
        and taken_metrics["expectancy"] is not None
        and taken_metrics["expectancy"] > 0
        and (taken_metrics["bootstrap_p05"] or -1) > 0
        and (taken_metrics["profit_factor"] or 0) > 1
        and (monotonicity or 0) >= 0.6
    )

    result: dict[str, Any] = {
        "schema": "predictor_protocol.v1",
        "train_n": int(len(inner)),
        "sealed_n": int(len(sealed)),
        "n_folds_inner": int(n_folds),
        "threshold_selection": choice,
        "locked_threshold": threshold,
        "threshold_source": choice.get("source"),
        "correlation_pearson": _pearson(pred_se, y_se),
        "correlation_spearman": _spearman(pred_se, y_se),
        "mae": round(float(np.mean(np.abs(pred_se - y_se))), 5),
        "rmse": round(float(np.sqrt(np.mean((pred_se - y_se) ** 2))), 5),
        "sealed_all": sealed_all_metrics,
        "sealed_taken": taken_metrics,
        "improvement_expectancy": round(
            (taken_metrics["expectancy"] or 0.0) - sealed_all_metrics["expectancy"], 5),
        "deciles": deciles,
        "monotonicity_fraction": monotonicity,
        "walk_forward_stability": wf_stability,
        "ml_advances": ml_advances,
        "note": ("taken set = sealed rows whose prediction clears the "
                 "inner-learned threshold; holdout touched once"),
    }

    # Optional grouped OOS performance on sealed window.
    if meta is not None:
        meta_se = meta.iloc[len(inner):len(inner) + len(sealed)]
        groups: dict[str, dict[str, Any]] = {}
        for col in ("symbol", "side", "session", "regime", "strategy_family"):
            if col not in meta_se.columns:
                continue
            by: dict[str, list[int]] = {}
            for i, val in enumerate(meta_se[col].astype(str)):
                by.setdefault(val, []).append(i)
            gout = {}
            for key, idxs in sorted(by.items()):
                arr = y_se[idxs]
                pr = pred_se[idxs]
                m = (pr >= threshold) if threshold is not None else np.zeros(len(pr), bool)
                gout[key] = {
                    "n": int(len(arr)),
                    "ev": round(float(arr.mean()), 5),
                    "taken_n": int(m.sum()),
                    "taken_ev": round(float(arr[m].mean()), 5) if m.any() else None,
                }
            groups[col] = gout
        result["sealed_grouped"] = groups

    result["equity_curve"] = [float(v) for v in np.cumsum(y_se)]
    result["drawdown"] = [float(v) for v in _drawdown_series(np.cumsum(y_se))]
    result["model_equity_curve"] = [float(v) for v in np.cumsum(taken)]
    return result


def ml_advances_from_protocol(protocol_result: dict[str, Any]) -> bool:
    """Single authority for the advance decision. Recomputes from sealed
    evidence - never trusts a stored boolean (audit defect 12 spirit)."""
    if protocol_result.get("locked_threshold") is None:
        return False
    taken = protocol_result.get("sealed_taken") or {}
    n = int(taken.get("n") or 0)
    exp = taken.get("expectancy")
    p05 = taken.get("bootstrap_p05")
    pf = taken.get("profit_factor")
    mono = protocol_result.get("monotonicity_fraction")
    return bool(
        n >= 20
        and exp is not None and float(exp) > 0
        and p05 is not None and float(p05) > 0
        and pf is not None and float(pf) > 1
        and mono is not None and float(mono) >= 0.6
    )
