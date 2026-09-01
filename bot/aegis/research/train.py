"""Point-in-time linear PnL filter. Research-only; not Jansen ML; not a 100% WR claim."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from aegis.research.costs import pnl_summary
from aegis.research.dataset import clips_from_journal
from aegis.research.evaluate import purged_holdout, untouched_holdout
from aegis.research.fingerprint import config_fingerprint
from aegis.research.gates import GateReject, evaluate_promotion
from aegis.research.stress import tail_stress


FEATURE_ORDER = (
    "spread",
    "qty",
    "side_buy",
    "hour_utc",
    "dow_utc",
    "intel_quality",
    "quote_age_s",
    "t2t_ms",
    "stop_tp_span",
    "reason_up",
    "session_london",
    "session_ny",
    "spread_x_hour",
)


def _clips_frame(clips: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for clip in clips:
        row = dict(clip["features"])
        row["symbol"] = clip["symbol"]
        row["side"] = clip["side"]
        row["time"] = clip["bar"]
        row["pnl"] = clip["pnl"]
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("no paired order/flatten clips")
    df = df.sort_values("time").reset_index(drop=True)
    return df


def _design(
    train: pd.DataFrame,
    hold: pd.DataFrame,
    feature_cols: Sequence[str] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    symbols = sorted(train["symbol"].astype(str).unique())
    x_cols = list(feature_cols) if feature_cols else list(FEATURE_ORDER)

    def matrix(part: pd.DataFrame) -> np.ndarray:
        base = part.loc[:, x_cols].astype(float).to_numpy()
        dummies = np.zeros((len(part), len(symbols)), dtype=float)
        for i, sym in enumerate(symbols):
            dummies[:, i] = (part["symbol"].astype(str) == sym).astype(float)
        return np.hstack([base, dummies])

    x_train = matrix(train)
    x_hold = matrix(hold)
    mu = x_train.mean(axis=0)
    sd = x_train.std(axis=0)
    sd = np.where(sd < 1e-12, 1.0, sd)
    return (x_train - mu) / sd, (x_hold - mu) / sd, mu, sd


def _ridge_fit(x: np.ndarray, y: np.ndarray, ridge: float) -> np.ndarray:
    n = x.shape[1] + 1
    xb = np.hstack([np.ones((x.shape[0], 1)), x])
    xtx = xb.T @ xb
    reg = float(ridge) * np.eye(n)
    reg[0, 0] = 0.0
    return np.linalg.pinv(xtx + reg) @ xb.T @ y


def _predict(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    xb = np.hstack([np.ones((x.shape[0], 1)), x])
    return xb @ weights


def train_pnl_filter(
    journal_path: Path,
    *,
    holdout_frac: float = 0.3,
    ridge: float = 1.0,
) -> dict[str, Any]:
    clips = clips_from_journal(Path(journal_path))
    frame = _clips_frame(clips)
    train, hold = untouched_holdout(frame, holdout_frac=holdout_frac)
    if hold.empty or train.empty:
        raise ValueError("empty train or holdout after time split")
    x_train, x_hold, _, _ = _design(train, hold)
    y_train = train["pnl"].to_numpy(dtype=float)
    y_hold = hold["pnl"].to_numpy(dtype=float)
    weights = _ridge_fit(x_train, y_train, ridge)
    pred = _predict(x_hold, weights)
    take = pred > 0.0
    taken = y_hold[take]
    filtered = pnl_summary(taken.tolist())
    always = pnl_summary(y_hold.tolist())
    metrics = {
        "expectancy": filtered["expectancy"] if filtered["n"] else 0.0,
        "profit_factor": filtered["profit_factor"] if filtered["profit_factor"] is not None else 0.0,
        "n_trades": filtered["n"],
        "net_pnl": filtered["net_pnl"],
        "win_rate": filtered["win_rate"] if filtered["win_rate"] is not None else 0.0,
    }
    accepted = False
    reason = "not evaluated"
    try:
        evaluate_promotion(metrics, champion=None)
        accepted = True
        reason = "holdout gates passed (shadow only; not Jansen ML; not live)"
    except GateReject as exc:
        reason = str(exc)
    train_bar_max = pd.Timestamp(train["time"].max())
    holdout_bar_min = pd.Timestamp(hold["time"].min())
    return {
        "id": "exp_linear_pnl_filter",
        "hypothesis": (
            "Entry-only ridge filter on journal fields has holdout E>0 and PF>1 "
            "on paired firehose clips"
        ),
        "label": "research_proxy",
        "not_jansen_ml": True,
        "win_rate_is_not_the_objective": True,
        "promoted_live_yaml": False,
        "placed_orders": False,
        "mt5_touched": False,
        "accepted_shadow": accepted,
        "reason": reason,
        "n_clips": int(len(frame)),
        "n_train": int(len(train)),
        "n_holdout": int(len(hold)),
        "n_taken": int(filtered["n"]),
        "holdout_expectancy": metrics["expectancy"],
        "holdout_profit_factor": metrics["profit_factor"],
        "holdout_win_rate": metrics["win_rate"],
        "holdout_net_pnl": metrics["net_pnl"],
        "always_take_expectancy": always["expectancy"],
        "always_take_profit_factor": always["profit_factor"],
        "always_take_n": always["n"],
        "holdout_pnls": [float(x) for x in taken],
        "always_take_pnls": [float(x) for x in y_hold],
        "train_bar_max": train_bar_max.isoformat(),
        "holdout_bar_min": holdout_bar_min.isoformat(),
        "config_fingerprint": config_fingerprint({"model": "ridge_pnl", "ridge": ridge}),
        "weights_n": int(weights.size),
    }


MIN_HOLDOUT_TRADES = 20
MIN_SAMPLED_LOSSES = 5

_BASELINE_NAMES = {
    "bars": "legacy_firehose_always_take",
    "search": "journal_filter_always_take",
    "payoff": "payoff_sweep_always_take",
    "entries": "entry_family_always_take",
    "stack": "six_book_stack_always_take",
}


def named_always_take_baseline(trained: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    """Label the unfiltered holdout with the experiment kind. Never call a stack run firehose."""
    name = _BASELINE_NAMES.get(str(kind), f"{kind}_always_take")
    return {
        "name": name,
        "total_trades": trained.get("always_take_n"),
        "expectancy_r": trained.get("always_take_expectancy"),
        "profit_factor": trained.get("always_take_profit_factor"),
        "not_a_champion": True,
    }


def pick_sweep_winner(
    results: Sequence[Mapping[str, Any]],
    *,
    min_losses: int = MIN_SAMPLED_LOSSES,
) -> Mapping[str, Any] | None:
    """Best result among those whose loss tail was actually sampled.

    A payoff that produced only a couple of losses can post a spectacular expectancy
    by luck, so it is not eligible no matter how good it looks.
    """
    judgeable = [
        r for r in results if int(r.get("holdout_n_losses") or 0) >= int(min_losses)
    ]
    if not judgeable:
        return None
    return max(judgeable, key=lambda r: float(r.get("holdout_expectancy") or 0.0))


def rank_trials(
    trials: list[dict[str, Any]],
    *,
    min_trades: int = MIN_HOLDOUT_TRADES,
) -> tuple[list[dict[str, Any]], bool]:
    """Order trials best-first. A selection too small to judge can never rank first.

    Taking zero trades yields an expectancy of 0.0, which would otherwise beat every
    honestly-negative filter. Trials below `min_trades` are ranked last regardless of
    their score, and the caller is told whether any trial was large enough to judge.
    """

    def key(trial: dict[str, Any]) -> tuple[int, float, float, int]:
        n = int(trial.get("n_taken") or 0)
        return (
            1 if n >= int(min_trades) else 0,
            float(trial.get("expectancy") or 0.0),
            float(trial.get("profit_factor") or 0.0),
            n,
        )

    ordered = sorted(trials, key=key, reverse=True)
    qualifying = any(int(t.get("n_taken") or 0) >= int(min_trades) for t in trials)
    return ordered, qualifying


def _threshold_from_train(pred: np.ndarray, y: np.ndarray, *, min_take: int = 8) -> float:
    """Pick a take-threshold using train predictions only."""
    cands = [0.0]
    for q in (50.0, 60.0, 70.0, 80.0):
        cands.append(float(np.percentile(pred, q)))
    best_t = 0.0
    best_e = float("-inf")
    for t in dict.fromkeys(round(c, 12) for c in cands):
        taken = y[pred > t]
        if taken.size < min_take:
            continue
        e = float(taken.mean())
        if e > best_e:
            best_e = e
            best_t = float(t)
    return best_t


def _symbol_allowlist(train: pd.DataFrame) -> set[str]:
    allow: set[str] = set()
    for sym, part in train.groupby(train["symbol"].astype(str)):
        if float(part["pnl"].mean()) > 0:
            allow.add(str(sym))
    return allow


def _run_search(
    frame: pd.DataFrame,
    feature_cols: Sequence[str],
    *,
    holdout_frac: float,
    round_id: str,
    id_prefix: str,
    hypothesis: str,
    data_source: str,
    purged: bool = False,
    force_target: str | None = None,
) -> dict[str, Any]:
    """Shared grid search. Ranks by holdout expectancy, never by win rate."""
    cols = list(feature_cols)
    if not cols:
        raise ValueError("no feature columns to train on")
    frame = frame.dropna(subset=cols).reset_index(drop=True)
    split = purged_holdout if purged else untouched_holdout
    train, hold = split(frame, holdout_frac=holdout_frac)
    if hold.empty or train.empty:
        raise ValueError("empty train or holdout after time split")
    y_hold_all = hold["pnl"].to_numpy(dtype=float)
    always = pnl_summary(y_hold_all.tolist())
    trials: list[dict[str, Any]] = []
    grid = [
        (ridge, target, drop_neg, skip_asia)
        for ridge in (0.01, 0.1, 1.0, 10.0)
        for target in ((force_target,) if force_target else ("pnl", "win"))
        for drop_neg in (False, True)
        for skip_asia in (False, True)
    ]
    for ridge, target, drop_neg, skip_asia in grid:
        x_train, x_hold, _, _ = _design(train, hold, cols)
        y_fit = train["pnl"].to_numpy(dtype=float)
        if target == "win":
            y_fit = (y_fit > 0.0).astype(float)
        weights = _ridge_fit(x_train, y_fit, ridge)
        pred_train = _predict(x_train, weights)
        pred_hold = _predict(x_hold, weights)
        thresh = _threshold_from_train(pred_train, train["pnl"].to_numpy(dtype=float))
        take = pred_hold > thresh
        if drop_neg:
            allow = _symbol_allowlist(train)
            take = take & hold["symbol"].astype(str).isin(allow).to_numpy()
        if skip_asia:
            take = take & (hold["hour_utc"].to_numpy() >= 7.0)
        taken = y_hold_all[take]
        stats = pnl_summary(taken.tolist())
        e = stats["expectancy"] if stats["n"] else 0.0
        pf = stats["profit_factor"] if stats["profit_factor"] is not None else 0.0
        trials.append(
            {
                "ridge": ridge,
                "target": target,
                "drop_neg_symbols": drop_neg,
                "skip_asia": skip_asia,
                "threshold": thresh,
                "n_taken": stats["n"],
                "expectancy": e,
                "profit_factor": pf,
                "win_rate": stats["win_rate"],
                "net_pnl": stats["net_pnl"],
                "holdout_pnls": [float(x) for x in taken],
            }
        )
    trials, has_qualifying = rank_trials(trials, min_trades=MIN_HOLDOUT_TRADES)
    best = trials[0]
    metrics = {
        "expectancy": float(best["expectancy"] or 0.0),
        "profit_factor": float(best["profit_factor"] or 0.0),
        "n_trades": int(best["n_taken"] or 0),
        "net_pnl": float(best["net_pnl"] or 0.0),
        "win_rate": float(best["win_rate"] or 0.0),
    }
    tail = tail_stress(best["holdout_pnls"])
    accepted = False
    reason = "not evaluated"
    try:
        evaluate_promotion(metrics, champion=None)
        accepted = True
        reason = (
            "expectancy/PF/min-trade gates passed; the tail gate is applied by the cycle"
        )
    except GateReject as exc:
        reason = str(exc)
    if not has_qualifying:
        reason = (
            f"no trial reached {MIN_HOLDOUT_TRADES} holdout trades; "
            f"best kept only {int(best['n_taken'])}"
        )
    return {
        "id": f"{id_prefix}_{round_id}",
        "hypothesis": hypothesis,
        "label": "research_proxy",
        "not_jansen_ml": True,
        "meta_label": bool(force_target == "win"),
        "win_rate_is_not_the_objective": True,
        "rank_metric": "holdout_expectancy",
        "data_source": data_source,
        "purged_holdout": bool(purged),
        "feature_cols": cols,
        "min_holdout_trades": MIN_HOLDOUT_TRADES,
        "has_qualifying_trial": has_qualifying,
        "n_searches": len(trials),
        "promoted_live_yaml": False,
        "placed_orders": False,
        "mt5_touched": False,
        "accepted_shadow": accepted,
        "reason": reason,
        "n_clips": int(len(frame)),
        "n_train": int(len(train)),
        "n_holdout": int(len(hold)),
        "n_taken": int(best["n_taken"]),
        "best": {k: v for k, v in best.items() if k != "holdout_pnls"},
        "holdout_expectancy": metrics["expectancy"],
        "holdout_profit_factor": metrics["profit_factor"],
        "holdout_win_rate": metrics["win_rate"],
        "holdout_net_pnl": metrics["net_pnl"],
        "holdout_n_losses": int(tail["n_losses"]),
        "holdout_worst_loss": tail["worst_loss"],
        "holdout_pnls": best["holdout_pnls"],
        "always_take_expectancy": always["expectancy"],
        "always_take_profit_factor": always["profit_factor"],
        "always_take_n": always["n"],
        "train_bar_max": pd.Timestamp(train["time"].max()).isoformat(),
        "holdout_bar_min": pd.Timestamp(hold["time"].min()).isoformat(),
        "config_fingerprint": config_fingerprint(
            {"model": "ridge_search", "round": round_id, "best": best.get("ridge")}
        ),
        "trial_expectancies": [t["expectancy"] for t in trials],
    }


def search_pnl_filters(
    journal_path: Path,
    *,
    holdout_frac: float = 0.3,
    round_id: str = "r0",
    purged: bool = False,
) -> dict[str, Any]:
    """Search filters over live-journal execution metadata only (no price context)."""
    frame = _clips_frame(clips_from_journal(Path(journal_path)))
    return _run_search(
        frame,
        FEATURE_ORDER,
        holdout_frac=holdout_frac,
        round_id=round_id,
        id_prefix="exp_linear_pnl_search",
        hypothesis=(
            "Grid of entry-only ridge/win filters on journal metadata, threshold fit "
            "on train, ranked by holdout E not WR, has E>0 and PF>1"
        ),
        data_source="live_journal",
        purged=purged,
    )


def search_meta_label_filters(
    clips: Sequence[Mapping[str, Any]],
    *,
    holdout_frac: float = 0.3,
    round_id: str = "m0",
    data_source: str = "mt5_bars",
    purged: bool = True,
) -> dict[str, Any]:
    """Prado meta-label: predict profitable primary trades (win/loss), not raw PnL level."""
    from aegis.research.barclips import clips_frame, market_state_columns

    frame = clips_frame(clips)
    cols = market_state_columns(clips)
    return _run_search(
        frame,
        cols,
        holdout_frac=holdout_frac,
        round_id=round_id,
        id_prefix="exp_meta_label_search",
        hypothesis=(
            "Prado meta-label ridge on signal-bar state: fit win/loss on train, "
            "rank by holdout E not WR, purged split by default"
        ),
        data_source=data_source,
        purged=purged,
        force_target="win",
    )


def search_bar_clip_filters(
    clips: Sequence[Mapping[str, Any]],
    *,
    holdout_frac: float = 0.3,
    round_id: str = "b0",
    data_source: str = "mt5_bars",
    purged: bool = False,
) -> dict[str, Any]:
    """Search filters over market state at the signal bar (replayed bars, not the journal)."""
    from aegis.research.barclips import clips_frame, market_state_columns

    frame = clips_frame(clips)
    return _run_search(
        frame,
        market_state_columns(clips),
        holdout_frac=holdout_frac,
        round_id=round_id,
        id_prefix="exp_barclip_search",
        hypothesis=(
            "Grid of ridge/win filters on signal-bar market state from replayed bars, "
            "threshold fit on train, ranked by holdout E not WR, has E>0 and PF>1"
        ),
        data_source=data_source,
        purged=purged,
    )
