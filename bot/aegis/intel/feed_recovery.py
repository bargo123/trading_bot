"""Bounded recovery for a genuinely stalled MT5 raw quote feed.

This module only probes raw broker ticks, refreshes Market Watch, and asks the
existing engine to reconnect.  It does not change candidate selection or send
orders.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Callable


@dataclass(frozen=True)
class FeedRecoveryResult:
    status: str
    stage: str
    reason: str
    attempts: int
    advanced_symbols: list[str]
    details: dict[str, Any]

    @property
    def success(self) -> bool:
        return self.status == "HEALTHY"


def _signature(tick: Any) -> tuple[object, object, object]:
    if not isinstance(tick, dict):
        return (None, None, None)
    return (
        tick.get("time_msc"),
        tick.get("bid"),
        tick.get("ask"),
    )


def _advanced(before: Any, after: Any) -> bool:
    previous = _signature(before)
    current = _signature(after)
    if current == (None, None, None):
        return False
    if previous == (None, None, None):
        return True
    old_msc, old_bid, old_ask = previous
    new_msc, new_bid, new_ask = current
    try:
        if new_msc is not None and old_msc is not None and int(new_msc) > int(old_msc):
            return True
    except (TypeError, ValueError):
        pass
    return (new_bid, new_ask) != (old_bid, old_ask)


def _probe_raw_feed(
    engine: Any,
    symbols: list[str],
    *,
    stage: str,
    probe_seconds: float,
    poll_seconds: float,
    monotonic_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
    baseline: Mapping[str, Any] | None = None,
) -> FeedRecoveryResult:
    raw_tick = getattr(engine, "raw_tick", None)
    if not callable(raw_tick):
        return FeedRecoveryResult(
            "RECOVERY_FAILED", stage, "raw_tick_unavailable", 0, [], {}
        )
    initial: dict[str, Any] = dict(baseline or {})
    errors: dict[str, str] = {}
    if baseline is None:
        for symbol in symbols:
            try:
                initial[symbol] = raw_tick(symbol)
            except Exception as exc:
                initial[symbol] = None
                errors[symbol] = f"{type(exc).__name__}:{exc}"

    advanced: set[str] = set()
    attempts = 0
    deadline = monotonic_fn() + max(0.0, float(probe_seconds))
    while True:
        for symbol in symbols:
            try:
                current = raw_tick(symbol)
                attempts += 1
                if _advanced(initial.get(symbol), current):
                    advanced.add(symbol)
            except Exception as exc:
                attempts += 1
                errors[symbol] = f"{type(exc).__name__}:{exc}"
        if len(advanced) == len(symbols):
            return FeedRecoveryResult(
                "HEALTHY", stage, "raw_tick_advanced", attempts,
                [symbol for symbol in symbols if symbol in advanced],
                {"errors": errors},
            )
        if monotonic_fn() >= deadline:
            break
        sleep_fn(max(0.0, min(float(poll_seconds), deadline - monotonic_fn())))

    return FeedRecoveryResult(
        "FEED_STALLED", stage, "raw_tick_not_advancing", attempts,
        [symbol for symbol in symbols if symbol in advanced],
        {"errors": errors},
    )


def recover_stalled_feed(
    engine: Any,
    symbols: list[str],
    *,
    probe_seconds: float = 2.0,
    poll_seconds: float = 0.2,
    reconnect_backoff_s: float = 1.0,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> FeedRecoveryResult:
    """Refresh, probe, then reconnect once if raw benchmark ticks stay stalled."""
    benchmarks = [str(symbol) for symbol in symbols if str(symbol)]
    if not benchmarks:
        return FeedRecoveryResult(
            "RECOVERY_FAILED", "NONE", "no_benchmark_symbols", 0, [], {}
        )
    refresh = getattr(engine, "refresh_symbols", None)
    if not callable(refresh):
        return FeedRecoveryResult(
            "RECOVERY_FAILED", "MARKET_WATCH", "refresh_symbols_unavailable", 0, [], {}
        )
    refresh_error = None
    try:
        refresh(benchmarks)
    except Exception as exc:
        refresh_error = f"{type(exc).__name__}:{exc}"

    stage_two = _probe_raw_feed(
        engine,
        benchmarks,
        stage="MARKET_WATCH",
        probe_seconds=probe_seconds,
        poll_seconds=poll_seconds,
        monotonic_fn=monotonic_fn,
        sleep_fn=sleep_fn,
    )
    if stage_two.success:
        return FeedRecoveryResult(
            stage_two.status, stage_two.stage, stage_two.reason, stage_two.attempts,
            stage_two.advanced_symbols,
            {"refresh_error": refresh_error, **stage_two.details},
        )

    raw_tick = getattr(engine, "raw_tick", None)
    if stage_two.reason == "raw_tick_unavailable" or not callable(raw_tick):
        return FeedRecoveryResult(
            "RECOVERY_FAILED", stage_two.stage, stage_two.reason,
            stage_two.attempts, stage_two.advanced_symbols,
            {"refresh_error": refresh_error, **stage_two.details},
        )

    reconnect = getattr(engine, "reinitialize_connection", None)
    if not callable(reconnect):
        return FeedRecoveryResult(
            "RECOVERY_FAILED", "REINITIALIZE", "reinitialize_unavailable",
            stage_two.attempts, stage_two.advanced_symbols,
            {"refresh_error": refresh_error, **stage_two.details},
        )
    pre_reconnect: dict[str, Any] = {}
    for symbol in benchmarks:
        try:
            pre_reconnect[symbol] = raw_tick(symbol)
        except Exception:
            pre_reconnect[symbol] = None
    try:
        reconnect(symbols=benchmarks, backoff_s=max(0.0, float(reconnect_backoff_s)))
    except Exception as exc:
        return FeedRecoveryResult(
            "RECOVERY_FAILED", "REINITIALIZE", f"{type(exc).__name__}:{exc}",
            stage_two.attempts, stage_two.advanced_symbols,
            {"refresh_error": refresh_error, **stage_two.details},
        )

    stage_three = _probe_raw_feed(
        engine,
        benchmarks,
        stage="REINITIALIZE",
        probe_seconds=probe_seconds,
        poll_seconds=poll_seconds,
        monotonic_fn=monotonic_fn,
        sleep_fn=sleep_fn,
        baseline=pre_reconnect,
    )
    return FeedRecoveryResult(
        stage_three.status if stage_three.success else "RECOVERY_FAILED",
        stage_three.stage,
        stage_three.reason,
        stage_two.attempts + stage_three.attempts,
        stage_three.advanced_symbols,
        {
            "refresh_error": refresh_error,
            "stage_market_watch": stage_two.details,
            "stage_reinitialize": stage_three.details,
        },
    )
