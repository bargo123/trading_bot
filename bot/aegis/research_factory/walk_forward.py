"""Expanding, timestamp-purged walk-forward evaluation with observed costs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

import pandas as pd

from aegis.research_factory.replay import ReplayCostEvidence, replay_hypothesis
from aegis.research_factory.rules import CompileResult


@dataclass(frozen=True)
class WalkForwardFold:
    train_start: Any
    train_end: Any
    validation_start: Any
    validation_end: Any
    train_samples: int
    validation_samples: int
    trade_count: Optional[int]
    gross_pnl_usd: Optional[float]
    cost_usd: Optional[float]
    net_pnl_usd: Optional[float]
    expectancy_usd: Optional[float]
    max_drawdown_usd: Optional[float]
    status: str
    reason: str


@dataclass(frozen=True)
class WalkForwardResult:
    status: str
    reason: str
    folds: tuple[WalkForwardFold, ...]
    metrics: Optional[Mapping[str, float]]


def _result(status: str, reason: str) -> WalkForwardResult:
    return WalkForwardResult(status, reason, (), None)


def _predictions(pipeline: Any, validation: pd.DataFrame) -> pd.Series:
    predictions = pipeline.predict(validation)
    if not isinstance(predictions, Mapping) or not predictions:
        raise ValueError("ML pipeline produced no predictions")
    values = []
    for model in predictions.values():
        if not isinstance(model, Mapping) or "pred" not in model:
            raise ValueError("ML pipeline prediction is missing pred values")
        prediction = pd.Series(model["pred"])
        if len(prediction) != len(validation) or prediction.isna().any():
            raise ValueError("ML pipeline prediction does not match validation rows")
        values.append(prediction.astype(bool).astype(int))
    return pd.concat(values, axis=1).mean(axis=1).ge(0.5).set_axis(validation.index)


def _fold(frame: pd.DataFrame, replay: Any) -> WalkForwardFold:
    metrics = replay.metrics or {}
    return WalkForwardFold(
        train_start=frame["train"]["time"].min(),
        train_end=frame["train"]["time"].max(),
        validation_start=frame["validation"]["time"].min(),
        validation_end=frame["validation"]["time"].max(),
        train_samples=len(frame["train"]),
        validation_samples=len(frame["validation"]),
        trade_count=int(metrics["trade_count"]) if "trade_count" in metrics else None,
        gross_pnl_usd=metrics.get("gross_pnl_usd"),
        cost_usd=metrics.get("cost_usd"),
        net_pnl_usd=metrics.get("net_pnl_usd"),
        expectancy_usd=metrics.get("expectancy_usd"),
        max_drawdown_usd=metrics.get("max_drawdown_usd"),
        status=replay.status,
        reason=replay.reason,
    )


def _aggregate(folds: tuple[WalkForwardFold, ...]) -> Optional[Mapping[str, float]]:
    observed = [fold for fold in folds if fold.net_pnl_usd is not None]
    if not observed:
        return None
    trade_count = sum(fold.trade_count or 0 for fold in observed)
    net_pnl = sum(fold.net_pnl_usd or 0.0 for fold in observed)
    return {
        "trade_count": float(trade_count),
        "gross_pnl_usd": sum(fold.gross_pnl_usd or 0.0 for fold in observed),
        "cost_usd": sum(fold.cost_usd or 0.0 for fold in observed),
        "net_pnl_usd": net_pnl,
        "expectancy_usd": net_pnl / trade_count if trade_count else 0.0,
        "max_drawdown_usd": max(fold.max_drawdown_usd or 0.0 for fold in observed),
    }


def walk_forward_evaluate(
    frame: pd.DataFrame,
    *,
    pipeline_factory: Callable[[], Any],
    compiled: Optional[CompileResult],
    costs: Optional[ReplayCostEvidence],
    min_train_timestamps: int,
    validation_timestamps: int,
    step_timestamps: int,
) -> WalkForwardResult:
    """Retrain on each expanding prefix and replay only its next time slice."""
    if costs is None:
        return _result("NO_EVIDENCE", "walk-forward replay cost evidence is required")
    if compiled is None or compiled.status != "EXECUTABLE":
        return _result("NOT_EXECUTABLE", "an executable compiled hypothesis is required")
    if frame.empty:
        return _result("NO_DATA", "walk-forward frame is empty")
    if "time" not in frame.columns:
        return _result("NO_DATA", "walk-forward frame requires timestamps")
    if min(min_train_timestamps, validation_timestamps, step_timestamps) <= 0:
        return _result("FAILED", "walk-forward timestamp sizes must be positive")

    working = frame.copy()
    working["time"] = pd.to_datetime(working["time"], utc=True, errors="coerce")
    if working["time"].isna().any():
        return _result("NO_DATA", "walk-forward timestamps must be valid")
    working = working.sort_values("time", kind="stable")
    timestamps = pd.Index(working["time"].drop_duplicates().sort_values())
    if len(timestamps) < min_train_timestamps + validation_timestamps:
        return _result("NO_DATA", "insufficient timestamps for a walk-forward fold")

    folds = []
    for start in range(min_train_timestamps, len(timestamps) - validation_timestamps + 1, step_timestamps):
        train_times = timestamps[:start]
        validation_times = timestamps[start : start + validation_timestamps]
        train = working.loc[working["time"].isin(train_times)].copy()
        validation = working.loc[working["time"].isin(validation_times)].copy()
        try:
            pipeline = pipeline_factory()
            models = pipeline.train(train)
            if not models:
                raise ValueError("ML training produced no trained models")
            validation_signals = _predictions(pipeline, validation)
            # Keep prefix bars solely as indicator context; no prefix signal may trade.
            replay_frame = pd.concat([train, validation], ignore_index=True)
            signals = pd.Series(
                [False] * len(train) + validation_signals.tolist(),
                index=replay_frame.index,
            )
            replay = replay_hypothesis(
                replay_frame, compiled, costs, entry_signals=signals
            )
        except Exception as exc:
            class FailedReplay:
                status = "FAILED"
                metrics = None
                reason = f"walk-forward fold failed: {exc}"
            replay = FailedReplay()
        folds.append(_fold({"train": train, "validation": validation}, replay))

    observed_folds = tuple(folds)
    metrics = _aggregate(observed_folds)
    statuses = {fold.status for fold in observed_folds}
    for status in ("NO_EVIDENCE", "NOT_EXECUTABLE", "FAILED", "NO_DATA"):
        if status in statuses:
            reason = next(fold.reason for fold in observed_folds if fold.status == status)
            return WalkForwardResult(status, reason, observed_folds, metrics)
    if metrics is None or metrics["trade_count"] == 0:
        return WalkForwardResult("REJECTED", "no observed replay trades", observed_folds, metrics)
    if metrics["net_pnl_usd"] <= 0:
        return WalkForwardResult("REJECTED", "observed net replay PnL is not positive", observed_folds, metrics)
    return WalkForwardResult("CHALLENGER", "observed net replay PnL is positive", observed_folds, metrics)
