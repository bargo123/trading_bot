"""Read-only, multi-market shadow replay for seconds-horizon edge research.

This module deliberately has no broker/execution imports.  Every candidate is
an observed quote entry, and every outcome is replayed sequentially using the
executable opposite-side quote.  The resulting leaderboard is evidence only;
it cannot authorize a Firehose order.
"""
from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.linear_model import Ridge
from sklearn.isotonic import IsotonicRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from aegis.research.short_horizon import _session_name
from aegis.research.short_horizon_artifact import _feature_frame
from aegis.intel.trade_controller import TradeController


SHADOW_HORIZONS_S = (1, 2, 3, 5, 8, 10, 15, 20)
SHADOW_THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.925, 0.95, 0.975, 0.99)
SPREAD_VOL_GATE_THRESHOLDS = tuple(
    (spread_to_realized, spread_to_micro)
    for spread_to_realized in (0.05, 0.10, 0.15, 0.20)
    for spread_to_micro in (0.5, 1.0, 1.5, 2.0)
)
SOFT_SPREAD_VOL_GATE_SCORE_THRESHOLDS = (0.50, 0.60, 0.70, 0.80, 0.90)
SHADOW_EXIT_POLICIES = (
    "captured_exit_replay", "first_meaningful_green", "mfe_protection", "no_progress_3s",
)
SHADOW_PROBABILITY_TARGETS = {
    "P_GREEN_1S": "green_within_1s",
    "P_GREEN_2S": "green_within_2s",
    "P_GREEN_3S": "green_within_3s",
    "P_GREEN_5S": "green_within_5s",
    "P_GREEN_8S": "green_within_8s",
    "P_GREEN_10S": "green_within_10s",
    "P_CAPTURED_WIN_3S": "captured_win_3s",
    "P_CAPTURED_WIN_5S": "captured_win_5s",
    "P_CAPTURED_WIN_10S": "captured_win_10s",
    "P_CAPTURED_WIN_20S": "captured_win_20s",
    "P_IMMEDIATE_ADVERSE_MOVE": "immediate_adverse_move",
    "P_NEVER_GREEN": "never_green",
    "P_TAIL_LOSS": "tail_loss",
    "P_WINNER_GIVEBACK": "winner_giveback",
}
SHADOW_REGRESSION_TARGETS = {
    "EXPECTED_NET_PNL": "captured_exit_return",
    "EXPECTED_MFE": "mfe",
    "EXPECTED_MAE": "mae",
    "EXPECTED_TIME_TO_GREEN": "time_to_green_s",
    "EXPECTED_TIME_TO_FAILURE": "time_to_failure_s",
}

_OUTCOME_COLUMNS = frozenset(
    {
        "target", "terminal_net_pnl", "terminal_return", "mfe", "mae", "tail_loss",
        "harvest_return", "time_to_profit_s", "time_to_failure_s",
        "captured_exit_net_pnl", "captured_exit_return", "captured_exit_reason",
        "first_green", "never_green", "time_to_green_s", "time_to_mfe_s",
        "time_in_red_s", "winner_giveback", "future_path_observed_n",
        "first_profitable_executable_close", "first_profitable_close_net_pnl",
        "immediate_adverse_move",
    }
)


@dataclass(frozen=True)
class ShadowSlices:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    sealed: pd.DataFrame


def _add_completed_bar_context(features: pd.DataFrame) -> pd.DataFrame:
    """Attach only completed M1/M5/M15 quote-derived bars as-of each tick."""
    result = features.copy()
    quote = result.loc[:, ["time", "mid"]].sort_values("time", kind="stable")
    quote_indexed = quote.set_index("time")["mid"]
    for minutes in (1, 5, 15):
        bars = quote_indexed.resample(
            f"{minutes}min", label="right", closed="right"
        ).agg(["first", "max", "min", "last"]).dropna()
        bars = bars.rename(
            columns={
                "first": f"m{minutes}_open",
                "max": f"m{minutes}_high",
                "min": f"m{minutes}_low",
                "last": f"m{minutes}_close",
            }
        )
        bars[f"m{minutes}_return"] = bars[f"m{minutes}_close"] / bars[f"m{minutes}_open"] - 1.0
        bars[f"m{minutes}_range"] = bars[f"m{minutes}_high"] - bars[f"m{minutes}_low"]
        bars = bars.reset_index().rename(columns={"time": "bar_time"})
        result = pd.merge_asof(
            result.sort_values("time", kind="stable"),
            bars.sort_values("bar_time", kind="stable"),
            left_on="time", right_on="bar_time", direction="backward",
        ).drop(columns=["bar_time"])
        close = result[f"m{minutes}_close"]
        high = result[f"m{minutes}_high"]
        low = result[f"m{minutes}_low"]
        result[f"m{minutes}_close_location"] = np.divide(
            close - low, np.maximum(high - low, 1e-12)
        )
    m1_high = result["m1_high"].shift(1).rolling(20, min_periods=2).max()
    m1_low = result["m1_low"].shift(1).rolling(20, min_periods=2).min()
    result["structure_context"] = np.select(
        [result["m1_close"] > m1_high, result["m1_close"] < m1_low],
        ["m1_breakout_up", "m1_breakout_down"],
        default="m1_range_or_pullback",
    )
    result["regime_context"] = np.select(
        [result["volatility_expansion"] >= 1.2, result["volatility_expansion"] <= 0.8],
        ["volatility_expansion", "compression"],
        default="normal_volatility",
    )
    return result


def replay_executable_path(
    *,
    entry_time: Any,
    entry_bid: float,
    entry_ask: float,
    future_times: Sequence[Any],
    future_bid: Sequence[float],
    future_ask: Sequence[float],
    side: str,
    horizon_s: int,
    exit_policy: str = "captured_exit_replay",
) -> dict[str, Any]:
    """Replay a single entry with only the next quote visible at each step."""
    side = str(side).strip().lower()
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if int(horizon_s) <= 0:
        raise ValueError("horizon_s must be positive")
    exit_policy = str(exit_policy).strip().lower()
    valid_policies = {
        "captured_exit_replay", "first_meaningful_green", "mfe_protection",
        "no_progress_3s", "first_green",
    }
    if exit_policy not in valid_policies:
        raise ValueError(f"unsupported exit_policy: {exit_policy}")
    entry_timestamp = pd.Timestamp(entry_time)
    if entry_timestamp.tzinfo is None:
        entry_timestamp = entry_timestamp.tz_localize("UTC")
    else:
        entry_timestamp = entry_timestamp.tz_convert("UTC")
    times = pd.to_datetime(list(future_times), utc=True)
    bid = np.asarray(future_bid, dtype=float)
    ask = np.asarray(future_ask, dtype=float)
    if len(times) != len(bid) or len(times) != len(ask) or not len(times):
        raise ValueError("future quote arrays must be non-empty and aligned")
    entry = float(entry_ask if side == "buy" else entry_bid)
    entry_mid = (float(entry_bid) + float(entry_ask)) / 2.0
    entry_spread = max(float(entry_ask) - float(entry_bid), 1e-12)

    if exit_policy == "captured_exit_replay":
        # The executable target is the same controller used by the live
        # runner. Alternative research policies below remain explicitly
        # auxiliary and cannot become execution authority.
        replay = TradeController().replay_quote_path(
            quotes=[
                {"time": float(entry_timestamp.timestamp()), "bid": float(entry_bid), "ask": float(entry_ask)},
                *[
                    {"time": float(pd.Timestamp(timestamp).timestamp()), "bid": float(b), "ask": float(a)}
                    for timestamp, b, a in zip(times, bid, ask)
                ],
            ],
            side=side,
            horizon_s=horizon_s,
            target_price=entry + (2.0 * entry_spread if side == "buy" else -2.0 * entry_spread),
            stop_price=entry - (3.0 * entry_spread if side == "buy" else -3.0 * entry_spread),
            pip_size=entry_spread,
        )
        if replay.get("status") != "REPLAYED":
            raise ValueError(str(replay.get("reason") or "quote replay unavailable"))
        signed = bid - entry if side == "buy" else entry - ask
        replay_actions = list(replay.get("actions") or [])
        first_green_index = next(
            (i for i, action in enumerate(replay_actions)
             if float(action.get("net_pnl_usd", 0.0)) > 0.0),
            None,
        )
        first_failure_index = next((i for i, value in enumerate(signed) if value <= -3.0 * entry_spread), None)
        captured_time = float(replay["captured_exit_time_s"])
        return {
            "captured_exit_net_pnl": float(replay["captured_exit_net_pnl"]),
            "captured_exit_return": float(replay["captured_exit_net_pnl"]) / entry_mid if entry_mid > 0 else np.nan,
            "captured_exit_reason": str(replay["captured_exit_reason"]),
            "captured_exit_action": str(replay.get("captured_exit_action") or "TIMEOUT"),
            "terminal_net_pnl": float(replay["terminal_net_pnl"]),
            "terminal_return": float(replay["terminal_net_pnl"]) / entry_mid if entry_mid > 0 else np.nan,
            "mfe": float(np.max(signed)),
            "mae": float(np.min(signed)),
            "tail_loss": bool(np.min(signed) <= -3.0 * entry_spread),
            "immediate_adverse_move": bool(float(signed[0]) <= -entry_spread),
            "first_green": bool(first_green_index is not None),
            "never_green": bool(first_green_index is None),
            "time_to_green_s": replay.get("time_to_green_s"),
            "time_to_profit_s": replay.get("time_to_green_s"),
            "time_to_failure_s": (
                float((pd.Timestamp(times[first_failure_index]) - entry_timestamp).total_seconds())
                if first_failure_index is not None else None
            ),
            "time_to_mfe_s": replay.get("time_to_peak_s"),
            "time_in_red_s": float(sum(
                max(0.0, (pd.Timestamp(times[i]) - (entry_timestamp if i == 0 else pd.Timestamp(times[i - 1]))).total_seconds())
                for i, value in enumerate(signed) if float(value) < 0.0
            )),
            "winner_giveback": bool(np.max(signed) > 0.0 and float(replay["captured_exit_net_pnl"]) < np.max(signed)),
            "first_profitable_executable_close": bool(first_green_index is not None),
            "first_profitable_close_net_pnl": (
                float(replay_actions[first_green_index]["net_pnl_usd"])
                if first_green_index is not None else None
            ),
            "future_path_observed_n": int(len(replay.get("actions") or [])),
            "exit_policy": exit_policy,
            "exit_time_s": captured_time,
            "horizon_s": int(horizon_s),
            "controller_actions": list(replay.get("actions") or []),
        }
    signed = bid - entry if side == "buy" else entry - ask
    harvest_threshold = 2.0 * entry_spread
    abort_threshold = 3.0 * entry_spread
    first_green_index = next((i for i, value in enumerate(signed) if value > 0.0), None)
    first_failure_index = next((i for i, value in enumerate(signed) if value <= -3.0 * entry_spread), None)
    mfe_index = int(np.argmax(signed))
    captured = float(signed[-1])
    captured_reason = "timeout"
    captured_index: int | None = None
    time_in_red = 0.0
    seen_positive = False
    peak_after_green = -float("inf")
    prior = entry_timestamp
    for index, value in enumerate(signed):
        current = pd.Timestamp(times[index])
        elapsed = max(0.0, (current - prior).total_seconds())
        if float(value) < 0.0:
            time_in_red += elapsed
        prior = current
        elapsed_from_entry = max(0.0, (current - entry_timestamp).total_seconds())
        if float(value) > 0.0:
            seen_positive = True
        if float(value) <= -abort_threshold:
            captured = float(value)
            captured_reason = "abort"
            captured_index = index
            break
        if exit_policy == "no_progress_3s" and elapsed_from_entry >= 3.0 and not seen_positive:
            captured = float(value)
            captured_reason = "no_progress"
            captured_index = index
            break
        if exit_policy == "mfe_protection" and seen_positive:
            peak_after_green = max(peak_after_green, float(value))
            if peak_after_green >= harvest_threshold and float(value) <= peak_after_green - entry_spread:
                captured = float(value)
                captured_reason = "giveback"
                captured_index = index
                break
        harvest_now = (
            float(value) > 0.0 if exit_policy == "first_green"
            else float(value) >= harvest_threshold
        )
        if harvest_now and exit_policy != "mfe_protection":
            captured = float(value)
            captured_reason = "harvest"
            captured_index = index
            break
    mfe = float(np.max(signed))
    mae = float(np.min(signed))
    first_green = first_green_index is not None
    green_time = (
        float((pd.Timestamp(times[first_green_index]) - entry_timestamp).total_seconds())
        if first_green_index is not None else None
    )
    mfe_time = float((pd.Timestamp(times[mfe_index]) - entry_timestamp).total_seconds())
    failure_time = (
        float((pd.Timestamp(times[first_failure_index]) - entry_timestamp).total_seconds())
        if first_failure_index is not None else None
    )
    return {
        "captured_exit_net_pnl": captured,
        "captured_exit_return": captured / entry_mid if entry_mid > 0 else np.nan,
        "captured_exit_reason": captured_reason,
        "terminal_net_pnl": float(signed[-1]),
        "terminal_return": float(signed[-1]) / entry_mid if entry_mid > 0 else np.nan,
        "mfe": mfe,
        "mae": mae,
        "tail_loss": bool(mae <= -abort_threshold),
        "immediate_adverse_move": bool(float(signed[0]) <= -entry_spread),
        "first_green": bool(first_green),
        "never_green": bool(not first_green),
        "time_to_green_s": green_time,
        "time_to_profit_s": green_time,
        "time_to_failure_s": failure_time,
        "time_to_mfe_s": mfe_time,
        "time_in_red_s": float(time_in_red),
        "winner_giveback": bool(mfe > 0.0 and captured < mfe),
        "first_profitable_executable_close": bool(first_green),
        "first_profitable_close_net_pnl": (
            float(signed[first_green_index]) if first_green_index is not None else None
        ),
        "future_path_observed_n": int(len(signed) if captured_index is None else captured_index + 1),
        "exit_policy": exit_policy,
        "exit_time_s": float(
            (pd.Timestamp(times[captured_index]) - entry_timestamp).total_seconds()
            if captured_index is not None else (pd.Timestamp(times[-1]) - entry_timestamp).total_seconds()
        ),
        "horizon_s": int(horizon_s),
    }


def build_shadow_dataset(
    quotes_by_symbol: Mapping[str, pd.DataFrame],
    *,
    horizons: Sequence[int] = SHADOW_HORIZONS_S,
    sample_every_s: int = 1,
) -> pd.DataFrame:
    """Build all plausible quote-entry candidates across every supplied symbol."""
    horizon_values = tuple(sorted({int(value) for value in horizons if int(value) > 0}))
    if not horizon_values:
        raise ValueError("at least one positive horizon is required")
    if int(sample_every_s) <= 0:
        raise ValueError("sample_every_s must be positive")
    rows: list[dict[str, Any]] = []
    for raw_symbol, quotes in sorted(quotes_by_symbol.items()):
        symbol = str(raw_symbol).upper()
        try:
            features = _feature_frame(quotes, symbol)
        except ValueError as exc:
            # A malformed or non-varying broker history must not erase the
            # other symbols' evidence.  Keep the omission visible to callers.
            warnings.warn(f"shadow history skipped for {symbol}: {exc}", RuntimeWarning)
            continue
        features = _add_completed_bar_context(features)
        times = pd.to_datetime(features["time"], utc=True)
        # Use a relative seconds axis so pandas' ns/us resolution is harmless.
        epoch = (times - times.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        bid = features["bid"].to_numpy(dtype=float)
        ask = features["ask"].to_numpy(dtype=float)
        eligible = np.flatnonzero(epoch <= epoch[-1] - max(horizon_values))
        last_sample: float | None = None
        for index in eligible:
            if last_sample is not None and epoch[index] - last_sample < int(sample_every_s):
                continue
            last_sample = float(epoch[index])
            outcomes_by_side_horizon: dict[str, dict[int, dict[str, Any]]] = {
                "buy": {}, "sell": {}
            }
            for path_horizon in horizon_values:
                path_end = int(
                    np.searchsorted(epoch, epoch[index] + path_horizon, side="right") - 1
                )
                if path_end <= index:
                    continue
                for side in ("buy", "sell"):
                    outcomes_by_side_horizon[side][path_horizon] = replay_executable_path(
                        entry_time=times.iloc[index],
                        entry_bid=bid[index], entry_ask=ask[index],
                        future_times=times.iloc[index + 1 : path_end + 1],
                        future_bid=bid[index + 1 : path_end + 1],
                        future_ask=ask[index + 1 : path_end + 1],
                        side=side, horizon_s=path_horizon,
                    )
            for horizon in horizon_values:
                for side in ("buy", "sell"):
                    outcome = outcomes_by_side_horizon[side].get(horizon)
                    if outcome is None:
                        continue
                    row = features.iloc[index].to_dict()
                    row.update(outcome)
                    row.update(
                        {
                            "symbol": symbol,
                            "side": side,
                            "side_buy": 1.0 if side == "buy" else 0.0,
                            "horizon_s": float(horizon),
                            "entry_price": float(ask[index] if side == "buy" else bid[index]),
                            "entry_spread": float(ask[index] - bid[index]),
                            "cost": float(ask[index] - bid[index]),
                            "target": int(outcome["captured_exit_net_pnl"] > 0.0),
                            "session": _session_name(int(times.iloc[index].hour)),
                            "candidate_source": "all_quote_entries",
                            "candidate_authority": "SHADOW_ONLY",
                            "regime": str(features.iloc[index].get("regime_context") or "unknown_quote_regime"),
                            "structure": str(features.iloc[index].get("structure_context") or "unknown_structure"),
                            "family": "universal_quote_entry",
                            "family_version": "quote_microstructure_v1",
                        }
                    )
                    for policy in SHADOW_EXIT_POLICIES:
                        policy_end = int(
                            np.searchsorted(epoch, epoch[index] + horizon, side="right") - 1
                        )
                        policy_outcome = (
                            outcome if policy == "captured_exit_replay"
                            else replay_executable_path(
                                entry_time=times.iloc[index],
                                entry_bid=bid[index], entry_ask=ask[index],
                                future_times=times.iloc[index + 1 : policy_end + 1],
                                future_bid=bid[index + 1 : policy_end + 1],
                                future_ask=ask[index + 1 : policy_end + 1],
                                side=side, horizon_s=horizon, exit_policy=policy,
                            )
                        )
                        policy_key = policy.replace("_", "")
                        row[f"exit_{policy_key}_net_pnl"] = policy_outcome["captured_exit_net_pnl"]
                        row[f"exit_{policy_key}_return"] = policy_outcome["captured_exit_return"]
                        row[f"exit_{policy_key}_reason"] = policy_outcome["captured_exit_reason"]
                        row[f"exit_{policy_key}_time_s"] = policy_outcome["exit_time_s"]
                    # Carry every requested horizon's executable terminal
                    # path result on the row. These are outcome columns and
                    # never enter shadow_model_frame().
                    for path_horizon, path_outcome in outcomes_by_side_horizon[side].items():
                        row[f"pnl_{path_horizon}s"] = path_outcome["terminal_net_pnl"]
                        row[f"green_within_{path_horizon}s"] = bool(path_outcome["first_green"])
                        row[f"captured_win_{path_horizon}s"] = bool(
                            path_outcome["captured_exit_net_pnl"] > 0.0
                        )
                    rows.append(row)
    if not rows:
        raise ValueError("no matured shadow candidates")
    return pd.DataFrame(rows).sort_values(
        ["time", "symbol", "side", "horizon_s"], kind="stable"
    ).reset_index(drop=True)


def shadow_model_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the numeric point-in-time feature matrix plus the target."""
    if "target" not in frame:
        raise ValueError("shadow frame requires target")
    excluded = _OUTCOME_COLUMNS | frozenset(
        {
            "time", "symbol", "side", "session", "regime", "structure", "family",
            "family_version", "structure_context", "regime_context",
            "candidate_source", "candidate_authority",
        }
    )
    columns = [
        column for column in frame.columns
        if column not in excluded
        and not str(column).startswith(("pnl_", "green_within_", "captured_win_", "exit_"))
        and pd.api.types.is_numeric_dtype(frame[column])
    ]
    result = frame.loc[:, columns].copy()
    result["target"] = frame["target"].astype(int).to_numpy()
    return result.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def fast_winner_feature_discovery(
    frame: pd.DataFrame,
    *,
    horizons: Sequence[int] = (1, 2, 3, 5, 8, 10),
    top_n: int = 20,
) -> dict[str, Any]:
    """Describe point-in-time feature differences on sealed OOS outcomes.

    This is an evidence report only: future outcome columns define the groups
    after the replay, while the returned features come exclusively from the
    pre-entry model frame and are never fed back into training or execution.
    """
    if frame.empty:
        raise ValueError("fast-winner discovery requires observations")
    observations = frame.reset_index(drop=True)
    features = shadow_model_frame(observations).drop(columns=["target"]).reset_index(drop=True)
    captured = pd.to_numeric(observations.get("captured_exit_net_pnl"), errors="coerce").fillna(0.0)
    groups: dict[str, np.ndarray] = {}
    for horizon in horizons:
        green_column = f"green_within_{int(horizon)}s"
        green = observations.get(green_column, pd.Series(False, index=observations.index)).fillna(False).astype(bool)
        groups[f"fast_clean_winner_{int(horizon)}s"] = (green & (captured > 0.0)).to_numpy()
    first_green = observations.get("first_green", pd.Series(False, index=observations.index)).fillna(False).astype(bool)
    default_fast = next(iter(groups.values()), np.zeros(len(observations), dtype=bool))
    groups["fast_clean_winner"] = groups.get("fast_clean_winner_5s", default_fast)
    groups["slow_or_losing"] = ~groups["fast_clean_winner"]
    groups["never_green"] = (~first_green).to_numpy()
    groups["tail_loss"] = observations.get("tail_loss", pd.Series(False, index=observations.index)).fillna(False).astype(bool).to_numpy()
    groups["immediate_adverse_move"] = observations.get(
        "immediate_adverse_move", pd.Series(False, index=observations.index)
    ).fillna(False).astype(bool).to_numpy()
    groups["winner_giveback"] = observations.get(
        "winner_giveback", pd.Series(False, index=observations.index)
    ).fillna(False).astype(bool).to_numpy()

    feature_arrays = {
        str(column): pd.to_numeric(features[column], errors="coerce").to_numpy(dtype=float)
        for column in features.columns
    }
    horizons_report: dict[str, Any] = {}
    for horizon in horizons:
        fast = groups[f"fast_clean_winner_{int(horizon)}s"]
        comparison = groups["slow_or_losing"]
        rows: list[dict[str, Any]] = []
        for feature, values in feature_arrays.items():
            fast_values = values[fast & np.isfinite(values)]
            comparison_values = values[comparison & np.isfinite(values)]
            if not len(fast_values) or not len(comparison_values):
                continue
            fast_std = float(np.std(fast_values))
            comparison_std = float(np.std(comparison_values))
            pooled_std = float(np.sqrt((fast_std**2 + comparison_std**2) / 2.0))
            difference = float(np.mean(fast_values) - np.mean(comparison_values))
            rows.append(
                {
                    "feature": feature,
                    "comparison": "slow_or_losing",
                    "fast_mean": float(np.mean(fast_values)),
                    "comparison_mean": float(np.mean(comparison_values)),
                    "standardized_difference": difference / pooled_std if pooled_std > 0.0 else difference,
                }
            )
        rows.sort(key=lambda row: abs(row["standardized_difference"]), reverse=True)
        horizons_report[str(int(horizon))] = {
            "fast_clean_n": int(fast.sum()),
            "slow_or_losing_n": int(comparison.sum()),
            "top_feature_differences": rows[: max(1, int(top_n))],
        }
    return {
        "analysis_scope": "descriptive_sealed_oos",
        "groups": sorted(groups),
        "horizons": horizons_report,
        "features": list(feature_arrays),
        "note": "Outcome labels are used only to describe sealed OOS groups; no discovered feature authorizes execution.",
    }


def chronological_shadow_slices(frame: pd.DataFrame) -> ShadowSlices:
    if frame.empty or "time" not in frame:
        raise ValueError("shadow frame requires time")
    ordered = frame.sort_values("time", kind="stable").reset_index(drop=True)
    unique_times = ordered["time"].drop_duplicates().sort_values().to_numpy()
    if len(unique_times) < 20:
        raise ValueError("insufficient distinct timestamps for chronological OOS")
    train_end = unique_times[max(0, int(len(unique_times) * 0.60) - 1)]
    validation_end = unique_times[max(0, int(len(unique_times) * 0.80) - 1)]
    test_end = unique_times[max(0, int(len(unique_times) * 0.90) - 1)]
    parts = (
        ordered[ordered["time"] <= train_end].copy(),
        ordered[(ordered["time"] > train_end) & (ordered["time"] <= validation_end)].copy(),
        ordered[(ordered["time"] > validation_end) & (ordered["time"] <= test_end)].copy(),
        ordered[ordered["time"] > test_end].copy(),
    )
    if min(map(len, parts)) == 0:
        raise ValueError("chronological shadow slices must all be non-empty")
    return ShadowSlices(*parts)


def _calibration_ece(probability: np.ndarray, actual: np.ndarray) -> float | None:
    if not len(probability):
        return None
    ece = 0.0
    for lower in np.linspace(0.0, 1.0, 11)[:-1]:
        upper = lower + 0.1
        mask = (probability >= lower) & (probability < upper if upper < 1 else probability <= 1)
        if mask.any():
            ece += float(mask.mean()) * abs(float(probability[mask].mean()) - float(actual[mask].mean()))
    return float(ece)


def _calibrate_probability_vector(
    calibration_probability: np.ndarray,
    calibration_actual: np.ndarray,
    probability: np.ndarray,
) -> tuple[np.ndarray, str]:
    """Calibrate later predictions from the immediately prior OOS slice only."""
    raw = np.asarray(probability, dtype=float)
    prior_probability = np.asarray(calibration_probability, dtype=float)
    prior_actual = np.asarray(calibration_actual, dtype=int)
    if len(prior_probability) < 2 or len(np.unique(prior_actual)) < 2:
        return np.clip(raw, 0.0, 1.0), "identity_insufficient_calibration_data"
    calibrator = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    calibrator.fit(np.clip(prior_probability, 0.0, 1.0), prior_actual)
    return np.clip(calibrator.predict(np.clip(raw, 0.0, 1.0)), 0.0, 1.0), "isotonic_validation"


def _mean_confidence_bounds(values: np.ndarray, *, z: float = 1.96) -> tuple[float | None, float | None]:
    """Return a transparent normal-approximation 95% CI for a sample mean."""
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if len(finite) < 2:
        return None, None
    mean = float(finite.mean())
    standard_error = float(np.std(finite, ddof=1) / np.sqrt(len(finite)))
    margin = float(z) * standard_error
    return mean - margin, mean + margin


def _non_overlapping_selected(frame: pd.DataFrame, selected: np.ndarray) -> np.ndarray:
    """Keep a conservative single-slot subset of selected shadow candidates."""
    mask = np.asarray(selected, dtype=bool)
    keep = np.zeros(len(frame), dtype=bool)
    if not len(frame) or "time" not in frame:
        return keep
    if "_time_epoch_s" in frame:
        timestamps = pd.to_numeric(frame["_time_epoch_s"], errors="coerce").to_numpy(dtype=float)
    else:
        timestamps = pd.to_datetime(frame["time"], utc=True, errors="coerce").map(
            lambda value: value.timestamp() if pd.notna(value) else np.nan
        ).to_numpy(dtype=float)
    if "horizon_s" in frame:
        horizon_values = pd.to_numeric(frame["horizon_s"], errors="coerce").to_numpy(dtype=float)
    else:
        horizon_values = np.full(len(frame), np.nan, dtype=float)
    finite_horizons = horizon_values[np.isfinite(horizon_values) & (horizon_values > 0.0)]
    fallback_horizon_s = float(np.median(finite_horizons)) if len(finite_horizons) else 1.0
    next_available = None
    for index in np.argsort(timestamps, kind="stable"):
        if not mask[index] or not np.isfinite(timestamps[index]):
            continue
        if next_available is None or timestamps[index] >= next_available:
            keep[index] = True
            horizon_s = horizon_values[index]
            if not np.isfinite(horizon_s) or horizon_s <= 0.0:
                horizon_s = fallback_horizon_s
            next_available = timestamps[index] + float(horizon_s)
    return keep


def _metrics(
    frame: pd.DataFrame,
    probability: np.ndarray,
    threshold: float,
    *,
    duration_frame: pd.DataFrame | None = None,
    duration_hours: float | None = None,
) -> dict[str, Any]:
    probability = np.asarray(probability, dtype=float)
    actual = frame["target"].to_numpy(dtype=int)
    selected = probability >= float(threshold)
    captured = pd.to_numeric(frame["captured_exit_return"], errors="coerce").to_numpy(dtype=float)
    selected_values = captured[selected]
    executable_selected = _non_overlapping_selected(frame, selected)
    executable_values = captured[executable_selected]
    wins = selected_values[selected_values > 0.0]
    losses = selected_values[selected_values < 0.0]
    executable_wins = executable_values[executable_values > 0.0]
    executable_losses = executable_values[executable_values < 0.0]
    captured_lower_95, captured_upper_95 = _mean_confidence_bounds(selected_values)
    executable_lower_95, executable_upper_95 = _mean_confidence_bounds(executable_values)
    if duration_hours is None:
        duration_source = duration_frame if duration_frame is not None else frame
        ordered_times = (
            pd.to_datetime(duration_source["time"], utc=True, errors="coerce")
            if "time" in duration_source
            else pd.Series(dtype="datetime64[ns, UTC]")
        )
        duration_hours = (
            max(float((ordered_times.max() - ordered_times.min()).total_seconds()) / 3600.0, 1e-9)
            if len(ordered_times) and ordered_times.notna().all() else None
        )
    return {
        "n": int(len(frame)),
        "selected": int(selected.sum()),
        "precision": float(actual[selected].mean()) if selected.any() else None,
        "captured_exit_expectancy": float(selected_values.mean()) if len(selected_values) else None,
        "captured_exit_expectancy_lower_95": captured_lower_95,
        "captured_exit_expectancy_upper_95": captured_upper_95,
        "captured_exit_pf": float(wins.sum() / abs(losses.sum())) if len(wins) and len(losses) else None,
        "p95_loss": float(np.quantile(losses, 0.05)) if len(losses) else None,
        "p99_loss": float(np.quantile(losses, 0.01)) if len(losses) else None,
        "avg_win": float(wins.mean()) if len(wins) else None,
        "avg_loss": float(losses.mean()) if len(losses) else None,
        "median_time_to_green_s": float(pd.to_numeric(frame.loc[selected, "time_to_green_s"], errors="coerce").median())
        if selected.any() and "time_to_green_s" in frame else None,
        "trades_per_hour": float(executable_selected.sum() / duration_hours) if duration_hours else None,
        "net_per_hour": float(executable_values.sum() / duration_hours) if duration_hours and len(executable_values) else None,
        "candidate_arrivals_per_hour": float(selected.sum() / duration_hours) if duration_hours else None,
        "non_overlapping_selected": int(executable_selected.sum()),
        "executable_trades_per_hour": float(executable_selected.sum() / duration_hours) if duration_hours else None,
        "executable_net_per_hour": float(executable_values.sum() / duration_hours)
        if duration_hours and len(executable_values) else None,
        "executable_captured_exit_expectancy": float(executable_values.mean())
        if len(executable_values) else None,
        "executable_captured_exit_expectancy_lower_95": executable_lower_95,
        "executable_captured_exit_expectancy_upper_95": executable_upper_95,
        "executable_captured_exit_pf": float(executable_wins.sum() / abs(executable_losses.sum()))
        if len(executable_wins) and len(executable_losses) else None,
        "observation_window_hours": duration_hours,
        "exit_policy": "captured_exit_replay",
        "calibration_ece": _calibration_ece(probability, actual),
        "abstain_rate": float((~selected).mean()) if len(selected) else None,
    }


def evaluate_spread_vol_gates(
    frame: pd.DataFrame,
    *,
    thresholds: Sequence[tuple[float, float]] = SPREAD_VOL_GATE_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Evaluate ex-ante spread/volatility filters on chronological OOS slices."""
    required = {"spread_to_realized_vol", "spread_to_micro_vol"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"spread-vol gate requires features: {', '.join(missing)}")
    slices = chronological_shadow_slices(frame)
    rows: list[dict[str, Any]] = []
    for realized_limit, micro_limit in thresholds:
        def score(part: pd.DataFrame) -> dict[str, Any]:
            realized = pd.to_numeric(part["spread_to_realized_vol"], errors="coerce")
            micro = pd.to_numeric(part["spread_to_micro_vol"], errors="coerce")
            selected = (realized <= float(realized_limit)) & (micro <= float(micro_limit))
            return _metrics(
                part,
                selected.fillna(False).to_numpy(dtype=float),
                0.5,
                duration_frame=part,
            )

        rows.append(
            {
                "experiment": "spread_vol_gate_sweep",
                "spread_to_realized_vol_max": float(realized_limit),
                "spread_to_micro_vol_max": float(micro_limit),
                "execution_authority": "NONE",
                "test": score(slices.test),
                "sealed": score(slices.sealed),
            }
        )
    return rows


def evaluate_soft_spread_vol_gates(
    frame: pd.DataFrame,
    *,
    thresholds: Sequence[float] = SOFT_SPREAD_VOL_GATE_SCORE_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Evaluate a continuous spread/volatility score on chronological OOS slices.

    This is a research-only challenger to the hard ratio gates.  The score is
    monotone in both executable spread-to-volatility ratios and is never an
    execution authority or runtime filter.
    """
    required = {"spread_to_realized_vol", "spread_to_micro_vol"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"soft spread-vol gate requires features: {', '.join(missing)}")
    slices = chronological_shadow_slices(frame)
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        threshold_value = float(threshold)
        if not 0.0 <= threshold_value <= 1.0:
            raise ValueError("soft spread-vol score thresholds must be between 0 and 1")

        def score(part: pd.DataFrame) -> dict[str, Any]:
            realized = pd.to_numeric(part["spread_to_realized_vol"], errors="coerce")
            micro = pd.to_numeric(part["spread_to_micro_vol"], errors="coerce")
            soft_score = np.sqrt(
                (1.0 / (1.0 + realized.clip(lower=0.0)))
                * (1.0 / (1.0 + micro.clip(lower=0.0)))
            )
            selected = soft_score.ge(threshold_value) & soft_score.notna()
            return _metrics(
                part,
                selected.to_numpy(dtype=float),
                0.5,
                duration_frame=part,
            )

        rows.append(
            {
                "experiment": "spread_vol_soft_gate_sweep",
                "soft_gate_score_definition": "sqrt(1/(1+spread_to_realized_vol) * 1/(1+spread_to_micro_vol))",
                "soft_gate_score_threshold": threshold_value,
                "execution_authority": "NONE",
                "test": score(slices.test),
                "sealed": score(slices.sealed),
            }
        )
    return rows


def fit_multi_outcome_models(frame: pd.DataFrame) -> dict[str, Any]:
    """Fit point-in-time pooled probability/regression targets on sealed OOS.

    These are research diagnostics, not execution gates. Each target is fit
    only on the chronological training slice and scored on the sealed slice.
    """
    slices = chronological_shadow_slices(frame)
    train_features = shadow_model_frame(slices.train).drop(columns=["target"])
    validation_features = shadow_model_frame(slices.validation).drop(columns=["target"])
    test_features = shadow_model_frame(slices.test).drop(columns=["target"])
    sealed_features = shadow_model_frame(slices.sealed).drop(columns=["target"])
    report: dict[str, Any] = {"probability": {}, "regression": {}}

    def probability_metrics(
        actual: np.ndarray,
        probability: np.ndarray,
        *,
        status: str,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "oos_n": int(len(actual)),
            "oos_positive_rate": float(actual.mean()) if len(actual) else None,
            "oos_probability_mean": float(probability.mean()) if len(probability) else None,
            "oos_brier": float(np.mean(np.square(probability - actual))) if len(actual) else None,
            "calibration_ece": _calibration_ece(probability, actual),
        }

    def regression_metrics(
        actual: np.ndarray,
        prediction: np.ndarray,
        *,
        status: str,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "oos_n": int(len(actual)),
            "oos_prediction_mean": float(np.mean(prediction)) if len(prediction) else None,
            "oos_actual_mean": float(np.mean(actual)) if len(actual) else None,
            "oos_mae": float(np.mean(np.abs(prediction - actual))) if len(actual) else None,
        }

    for label, target_column in SHADOW_PROBABILITY_TARGETS.items():
        if target_column not in slices.train or target_column not in slices.sealed:
            report["probability"][label] = {"status": "missing_target", "target_column": target_column}
            continue
        y_train = pd.to_numeric(slices.train[target_column], errors="coerce").fillna(0.0).astype(int)
        y_sealed = pd.to_numeric(slices.sealed[target_column], errors="coerce").fillna(0.0).astype(int)
        if y_train.nunique() < 2:
            report["probability"][label] = {"status": "single_class_train", "target_column": target_column}
            continue
        model = Pipeline(
            [
                ("scale", RobustScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=0.1, solver="liblinear", max_iter=500,
                        class_weight="balanced", random_state=42,
                    ),
                ),
            ]
        )
        model.fit(train_features, y_train)
        validation_raw = model.predict_proba(validation_features)[:, 1]
        validation_actual = pd.to_numeric(
            slices.validation[target_column], errors="coerce"
        ).fillna(0.0).astype(int).to_numpy()
        test_raw = model.predict_proba(test_features)[:, 1]
        sealed_raw = model.predict_proba(sealed_features)[:, 1]
        test_probability, calibration_method = _calibrate_probability_vector(
            validation_raw, validation_actual, test_raw
        )
        sealed_probability, _ = _calibrate_probability_vector(
            validation_raw, validation_actual, sealed_raw
        )
        actual = y_sealed.to_numpy(dtype=int)
        test_actual = pd.to_numeric(
            slices.test[target_column], errors="coerce"
        ).fillna(0.0).astype(int).to_numpy()
        report["probability"][label] = {
            "status": "SEALED_OOS",
            "target_column": target_column,
            "model": "regularized_logistic",
            "calibration_method": calibration_method,
            **{
                key: value
                for key, value in probability_metrics(
                    actual, sealed_probability, status="SEALED_OOS"
                ).items()
                if key != "status"
            },
            "test": probability_metrics(test_actual, test_probability, status="TEST_OOS"),
            "sealed": probability_metrics(actual, sealed_probability, status="SEALED_OOS"),
        }
    for label, target_column in SHADOW_REGRESSION_TARGETS.items():
        if target_column not in slices.train or target_column not in slices.sealed:
            report["regression"][label] = {"status": "missing_target", "target_column": target_column}
            continue
        train_target = pd.to_numeric(slices.train[target_column], errors="coerce")
        sealed_target = pd.to_numeric(slices.sealed[target_column], errors="coerce")
        fill_value = float(train_target.median()) if train_target.notna().any() else 0.0
        y_train = train_target.fillna(fill_value).to_numpy(dtype=float)
        test_target = pd.to_numeric(slices.test[target_column], errors="coerce")
        y_sealed = sealed_target.fillna(fill_value).to_numpy(dtype=float)
        model = Pipeline([("scale", RobustScaler()), ("model", Ridge(alpha=1.0, solver="lsqr"))])
        model.fit(train_features, y_train)
        test_prediction = model.predict(test_features)
        prediction = model.predict(sealed_features)
        report["regression"][label] = {
            "status": "SEALED_OOS",
            "target_column": target_column,
            "model": "ridge",
            **{
                key: value
                for key, value in regression_metrics(
                    y_sealed, prediction, status="SEALED_OOS"
                ).items()
                if key != "status"
            },
            "test": regression_metrics(
                test_target.fillna(fill_value).to_numpy(dtype=float),
                test_prediction,
                status="TEST_OOS",
            ),
            "sealed": regression_metrics(y_sealed, prediction, status="SEALED_OOS"),
        }
    return report


def fit_segmented_logistic_models(
    frame: pd.DataFrame,
    *,
    min_train_samples: int = 200,
    min_validation_samples: int = 20,
    min_sealed_samples: int = 20,
) -> dict[str, Any]:
    """Fit small, chronological logistic challengers by supported dimensions.

    The pooled model remains the hierarchical fallback. Segment models are
    published as research evidence only and are never copied into runtime
    authority automatically.
    """
    slices = chronological_shadow_slices(frame)
    dimensions = ("symbol", "side", "session", "regime", "structure", "family", "horizon_s")
    x_train_all = shadow_model_frame(slices.train).drop(columns=["target"])
    x_validation_all = shadow_model_frame(slices.validation).drop(columns=["target"])
    x_sealed_all = shadow_model_frame(slices.sealed).drop(columns=["target"])
    rows: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}
    for dimension in dimensions:
        values = list(frame[dimension].dropna().unique())
        if len(values) <= 1:
            rejected[f"{dimension}:constant"] = 1
            continue
        for value in values:
            train_mask = slices.train[dimension] == value
            validation_mask = slices.validation[dimension] == value
            sealed_mask = slices.sealed[dimension] == value
            train_part = slices.train.loc[train_mask]
            validation_part = slices.validation.loc[validation_mask]
            sealed_part = slices.sealed.loc[sealed_mask]
            key = f"{dimension}={value}"
            if min(len(train_part), len(validation_part), len(sealed_part)) < min(
                min_train_samples, min_validation_samples, min_sealed_samples
            ):
                rejected[key] = 1
                continue
            y_train = train_part["target"].astype(int)
            if y_train.nunique() < 2:
                rejected[f"{key}:single_class"] = 1
                continue
            model = Pipeline(
                [
                    ("scale", RobustScaler()),
                    (
                        "model",
                        LogisticRegression(
                            C=0.1, solver="liblinear", max_iter=500,
                            class_weight="balanced", random_state=42,
                        ),
                    ),
                ]
            )
            model.fit(x_train_all.loc[train_mask.to_numpy()], y_train)
            validation_probability = model.predict_proba(
                x_validation_all.loc[validation_mask.to_numpy()]
            )[:, 1]
            validation_returns = validation_part["captured_exit_return"].to_numpy(dtype=float)
            candidates = [
                (float(validation_returns[validation_probability >= threshold].mean()), float(threshold))
                for threshold in SHADOW_THRESHOLDS
                if int((validation_probability >= threshold).sum()) >= int(min_validation_samples)
            ]
            threshold = max(candidates, default=(0.0, 0.5))[1]
            sealed_probability = model.predict_proba(x_sealed_all.loc[sealed_mask.to_numpy()])[:, 1]
            metrics = _metrics(
                sealed_part,
                sealed_probability,
                threshold,
                duration_frame=slices.sealed,
            )
            row = {
                "model": f"segmented_regularized_logistic_{dimension}",
                "segment_dimension": dimension,
                "segment_value": str(value),
                "threshold": threshold,
                **metrics,
            }
            for segment_dimension in dimensions:
                row[segment_dimension] = str(value) if segment_dimension == dimension else "ALL"
            rows.append(row)
    rows.sort(
        key=lambda row: (
            row["captured_exit_expectancy"] is None,
            -(row["captured_exit_expectancy"] or -float("inf")),
        )
    )
    return {
        "dimensions": list(dimensions),
        "accepted_model_count": len(rows),
        "rejected_segment_count": len(rejected),
        "rejected_segments": sorted(rejected)[:100],
        "oos_leaderboard": rows[:50],
    }


def evaluate_shadow_leaderboard(
    frame: pd.DataFrame,
    model_probabilities: Mapping[str, Sequence[float]],
    *,
    thresholds: Sequence[float] = SHADOW_THRESHOLDS,
    min_samples: int = 20,
) -> list[dict[str, Any]]:
    """Evaluate pooled model probabilities by universal market segment."""
    required = {"symbol", "side", "session", "regime", "structure", "family", "horizon_s"}
    if not required.issubset(frame.columns):
        raise ValueError(f"shadow frame missing segment columns: {sorted(required - set(frame.columns))}")
    work = frame.reset_index(drop=True).copy()
    work["_time_epoch_s"] = pd.to_datetime(work["time"], utc=True, errors="coerce").map(
        lambda value: value.timestamp() if pd.notna(value) else np.nan
    )
    work_times = pd.to_datetime(work["time"], utc=True, errors="coerce")
    observation_window_hours = max(
        float((work_times.max() - work_times.min()).total_seconds()) / 3600.0,
        1e-9,
    )
    rows: list[dict[str, Any]] = []
    group_columns = ["symbol", "side", "session", "regime", "structure", "family", "horizon_s"]
    for model_name, values in model_probabilities.items():
        probabilities = np.asarray(values, dtype=float)
        if len(probabilities) != len(frame):
            raise ValueError(f"probability length mismatch for {model_name}")
        for threshold in dict.fromkeys(float(value) for value in thresholds):
            for keys, group in work.groupby(group_columns, sort=False, dropna=False):
                indexes = group.index.to_numpy()
                metrics = _metrics(
                    group,
                    probabilities[indexes],
                    float(threshold),
                    duration_frame=work,
                    duration_hours=observation_window_hours,
                )
                if int(metrics["selected"]) < int(min_samples):
                    continue
                row = dict(zip(group_columns, keys))
                row.update({"model": str(model_name), "threshold": float(threshold), **metrics})
                rows.append(row)
    rows.sort(
        key=lambda row: (
            row["captured_exit_expectancy"] is None,
            -(row["captured_exit_expectancy"] or -float("inf")),
            -(row["selected"] or 0),
        )
    )
    return rows


def evaluate_exit_policies(
    frame: pd.DataFrame,
    *,
    policies: Sequence[str] = SHADOW_EXIT_POLICIES,
    min_samples: int = 20,
) -> list[dict[str, Any]]:
    """Compare causal exit policies on the supplied chronological slice."""
    required = {"symbol", "side", "session", "regime", "structure", "family", "horizon_s"}
    if not required.issubset(frame.columns):
        raise ValueError(f"shadow frame missing segment columns: {sorted(required - set(frame.columns))}")
    work = frame.reset_index(drop=True).copy()
    work["_time_epoch_s"] = pd.to_datetime(work["time"], utc=True, errors="coerce").map(
        lambda value: value.timestamp() if pd.notna(value) else np.nan
    )
    group_columns = ["symbol", "side", "session", "regime", "structure", "family", "horizon_s"]
    work_times = pd.to_datetime(work["time"], utc=True, errors="coerce")
    observation_window_hours = max(
        float((work_times.max() - work_times.min()).total_seconds()) / 3600.0,
        1e-9,
    )
    rows: list[dict[str, Any]] = []
    for policy in policies:
        policy_key = str(policy).replace("_", "")
        return_column = f"exit_{policy_key}_return"
        time_column = f"exit_{policy_key}_time_s"
        if return_column not in work or time_column not in work:
            raise ValueError(f"shadow frame missing policy outcome columns for {policy}")
        for keys, group in work.groupby(group_columns, sort=False, dropna=False):
            values_series = pd.to_numeric(group[return_column], errors="coerce").dropna()
            values = values_series.to_numpy(dtype=float)
            if len(values) < int(min_samples):
                continue
            wins = values[values > 0.0]
            losses = values[values < 0.0]
            row = dict(zip(group_columns, keys))
            executable_mask = _non_overlapping_selected(group.loc[values_series.index], np.ones(len(values), dtype=bool))
            executable_values = values[executable_mask]
            row.update(
                {
                    "exit_policy": str(policy),
                    "n": int(len(values)),
                    "win_rate": float((values > 0.0).mean()),
                    "captured_exit_expectancy": float(values.mean()),
                    "captured_exit_pf": float(wins.sum() / abs(losses.sum()))
                    if len(wins) and len(losses) else None,
                    "avg_win": float(wins.mean()) if len(wins) else None,
                    "avg_loss": float(losses.mean()) if len(losses) else None,
                    "p95_loss": float(np.quantile(losses, 0.05)) if len(losses) else None,
                    "p99_loss": float(np.quantile(losses, 0.01)) if len(losses) else None,
                    "median_exit_time_s": float(pd.to_numeric(group[time_column], errors="coerce").median()),
                    "trades_per_hour": float(len(executable_values) / observation_window_hours),
                    "net_per_hour": float(executable_values.sum() / observation_window_hours)
                    if len(executable_values) else None,
                    "candidate_arrivals_per_hour": float(len(values) / observation_window_hours),
                    "non_overlapping_selected": int(executable_mask.sum()),
                    "executable_trades_per_hour": float(len(executable_values) / observation_window_hours),
                    "executable_net_per_hour": float(executable_values.sum() / observation_window_hours)
                    if len(executable_values) else None,
                    "executable_captured_exit_expectancy": float(executable_values.mean())
                    if len(executable_values) else None,
                    "observation_window_hours": observation_window_hours,
                }
            )
            rows.append(row)
    rows.sort(
        key=lambda row: (
            row["captured_exit_expectancy"] is None,
            -(row["captured_exit_expectancy"] or -float("inf")),
        )
    )
    return rows


def dataset_hash(frame: pd.DataFrame) -> str:
    raw = frame.sort_values(["time", "symbol", "side", "horizon_s"], kind="stable").to_json(
        orient="records", date_format="iso", double_precision=15
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def fit_shadow_model_space(
    frame: pd.DataFrame,
    *,
    min_samples: int = 20,
) -> dict[str, Any]:
    """Fit local shadow-only model candidates on train and score sealed OOS."""
    slices = chronological_shadow_slices(frame)
    train, validation, sealed = slices.train, slices.validation, slices.sealed
    x_train = shadow_model_frame(train).drop(columns=["target"])
    x_validation = shadow_model_frame(validation).drop(columns=["target"])
    x_test = shadow_model_frame(slices.test).drop(columns=["target"])
    x_sealed = shadow_model_frame(sealed).drop(columns=["target"])
    y_train = train["target"].astype(int).to_numpy()
    if len(np.unique(y_train)) < 2:
        raise ValueError("shadow train target must contain both classes")
    factories = {
        "logistic": LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced", random_state=42),
        "regularized_logistic": LogisticRegression(C=0.1, max_iter=1000, class_weight="balanced", random_state=42),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=100, max_depth=5, learning_rate=0.05, random_state=42),
        "gradient_boosting": GradientBoostingClassifier(n_estimators=80, max_depth=3, learning_rate=0.05, random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=80, max_depth=8, class_weight="balanced", n_jobs=-1, random_state=42),
    }
    probabilities: dict[str, np.ndarray] = {}
    test_probabilities: dict[str, np.ndarray] = {}
    selected_thresholds: dict[str, float] = {}
    calibration_methods: dict[str, str] = {}
    model_errors: dict[str, str] = {}
    oos_metrics: dict[str, dict[str, Any]] = {}
    for name, estimator in factories.items():
        try:
            model = Pipeline([("scale", RobustScaler()), ("model", estimator)])
            model.fit(x_train, y_train)
            validation_raw = model.predict_proba(x_validation)[:, 1]
            validation_probability, calibration_method = _calibrate_probability_vector(
                validation_raw,
                validation["target"].astype(int).to_numpy(),
                validation_raw,
            )
            calibration_methods[name] = calibration_method
            candidates: list[tuple[float, float]] = []
            validation_captured = validation["captured_exit_return"].to_numpy(dtype=float)
            for threshold in SHADOW_THRESHOLDS:
                chosen = validation_probability >= threshold
                if int(chosen.sum()) >= int(min_samples):
                    candidates.append((float(validation_captured[chosen].mean()), float(threshold)))
            selected_thresholds[name] = max(candidates, default=(0.0, 0.5))[1]
            test_raw = model.predict_proba(x_test)[:, 1]
            test_probability, _ = _calibrate_probability_vector(
                validation_raw,
                validation["target"].astype(int).to_numpy(),
                test_raw,
            )
            test_probabilities[name] = test_probability
            sealed_raw = model.predict_proba(x_sealed)[:, 1]
            probabilities[name], _ = _calibrate_probability_vector(
                validation_raw,
                validation["target"].astype(int).to_numpy(),
                sealed_raw,
            )
            oos_metrics[name] = {
                "test": _metrics(slices.test, test_probability, selected_thresholds[name]),
                "sealed": _metrics(slices.sealed, probabilities[name], selected_thresholds[name]),
            }
        except Exception as exc:  # one model failure must not erase other evidence
            model_errors[name] = f"{type(exc).__name__}: {exc}"
    leaderboard = evaluate_shadow_leaderboard(
        sealed,
        probabilities,
        thresholds=tuple(selected_thresholds.values()) or (0.5,),
        min_samples=min_samples,
    )
    test_leaderboard = evaluate_shadow_leaderboard(
        slices.test,
        test_probabilities,
        thresholds=tuple(selected_thresholds.values()) or (0.5,),
        min_samples=min_samples,
    )
    test_by_key = {
        tuple(row.get(key) for key in ("symbol", "side", "session", "regime", "structure", "family", "horizon_s", "model", "threshold")): row
        for row in test_leaderboard
    }
    promotion_candidates: list[dict[str, Any]] = []
    for sealed_row in leaderboard:
        key = tuple(
            sealed_row.get(name)
            for name in ("symbol", "side", "session", "regime", "structure", "family", "horizon_s", "model", "threshold")
        )
        test_row = test_by_key.get(key)
        if not test_row:
            continue
        if (
            (sealed_row.get("captured_exit_expectancy") or 0.0) > 0.0
            and (test_row.get("captured_exit_expectancy") or 0.0) > 0.0
            and (sealed_row.get("captured_exit_pf") or 0.0) > 1.0
            and (test_row.get("captured_exit_pf") or 0.0) > 1.0
            and (sealed_row.get("executable_captured_exit_expectancy") or 0.0) > 0.0
            and (test_row.get("executable_captured_exit_expectancy") or 0.0) > 0.0
            and (sealed_row.get("executable_captured_exit_pf") or 0.0) > 1.0
            and (test_row.get("executable_captured_exit_pf") or 0.0) > 1.0
            and (sealed_row.get("executable_captured_exit_expectancy_lower_95") or 0.0) > 0.0
            and (test_row.get("executable_captured_exit_expectancy_lower_95") or 0.0) > 0.0
            and int(sealed_row.get("selected") or 0) >= int(min_samples)
            and int(test_row.get("selected") or 0) >= int(min_samples)
        ):
            promotion_candidates.append(
                {
                    "candidate": sealed_row,
                    "test": test_row,
                    "status": "REQUIRES_CALIBRATION_TAIL_REVIEW",
                }
            )
    primary_model = max(
        oos_metrics,
        key=lambda name: (
            oos_metrics[name]["sealed"].get("captured_exit_expectancy")
            if oos_metrics[name]["sealed"].get("captured_exit_expectancy") is not None
            else -float("inf")
        ),
        default=None,
    )
    multi_outcome_models = fit_multi_outcome_models(frame)
    segmented_model_space = fit_segmented_logistic_models(frame)
    sealed_predictions = slices.sealed.loc[
        :, [
            "time", "symbol", "side", "session", "regime", "structure", "family",
            "family_version", "horizon_s", "entry_price", "entry_spread", "cost",
        ]
    ].copy().reset_index(drop=True)
    probability_matrix: list[np.ndarray] = []
    for model_name in sorted(probabilities):
        values = np.asarray(probabilities[model_name], dtype=float)
        probability_matrix.append(values)
        sealed_predictions[f"model_probability_{model_name}"] = values
    if probability_matrix:
        matrix = np.vstack(probability_matrix).T
        sealed_predictions["model_probability_mean"] = matrix.mean(axis=1)
        sealed_predictions["model_disagreement"] = matrix.std(axis=1)
        sealed_predictions["prediction_vector"] = [list(map(float, row)) for row in matrix]
    sealed_predictions["prediction_split"] = "sealed_oos"
    return {
        "dataset_hash": dataset_hash(frame),
        "validation_hash": dataset_hash(validation),
        "feature_names": list(x_train.columns),
        "model_names": sorted(probabilities),
        "model_count": len(probabilities),
        "selected_thresholds": selected_thresholds,
        "calibration_methods": calibration_methods,
        "model_errors": model_errors,
        "oos_metrics": oos_metrics,
        "primary_model": primary_model,
        "multi_outcome_models": multi_outcome_models,
        "segmented_model_space": segmented_model_space,
        "sealed_predictions": sealed_predictions,
        "oos": {
            "train_n": len(train),
            "validation_n": len(validation),
            "test_n": len(slices.test),
            "sealed_n": len(sealed),
        },
        "leaderboard": leaderboard[:50],
        "test_leaderboard": test_leaderboard[:50],
        "promotion_candidates": promotion_candidates[:50],
    }
