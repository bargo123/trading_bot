"""Selective firehose pipeline: observe continuously, trade only with confluence."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from aegis.research.dataplane import resample_completed
from aegis.research.modules import collect_setups


@dataclass
class PipelineDecision:
    action: str
    stage: str
    reasons: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineContext:
    now: datetime
    quote_ts: datetime
    bid: float
    ask: float
    max_quote_age_s: float
    max_spread_pips: float
    pip_size: float
    take_pips: float
    portfolio_ok: bool
    m1: pd.DataFrame
    portfolio_reason: str = ""
    stop_pips: float = 0.0
    modeled_expectancy: float | None = None


def _age_s(now: datetime, ts: datetime) -> float:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds()


def classify_regime(h1: pd.DataFrame, pip: float) -> str:
    if h1.empty:
        return "noise"
    body = abs(float(h1["close"].iloc[-1]) - float(h1["open"].iloc[-1])) / pip
    rng = (float(h1["high"].iloc[-1]) - float(h1["low"].iloc[-1])) / pip
    if rng <= 0:
        return "noise"
    if body / rng < 0.25 and rng < 12:
        return "range"
    if body >= 8:
        return "trend"
    if rng >= 20 and body / rng >= 0.6:
        return "breakout"
    return "range"


def run_pipeline(ctx: PipelineContext) -> PipelineDecision:
    pip = max(float(ctx.pip_size), 1e-12)
    age = _age_s(ctx.now, ctx.quote_ts)
    if age < -0.25:
        return PipelineDecision("skip", "data_health", ["future_quote"])
    if age > float(ctx.max_quote_age_s):
        return PipelineDecision("skip", "data_health", ["stale_quote"])
    if ctx.ask <= ctx.bid:
        return PipelineDecision("skip", "data_health", ["crossed_quote"])
    spread_pips = (ctx.ask - ctx.bid) / pip
    if spread_pips > float(ctx.max_spread_pips):
        return PipelineDecision("skip", "data_health", ["wide_spread"])
    if spread_pips >= float(ctx.take_pips):
        return PipelineDecision("skip", "cost_health", ["spread_ge_take"])
    if not ctx.portfolio_ok:
        return PipelineDecision("skip", "portfolio_health", [ctx.portfolio_reason or "portfolio"])

    m5 = resample_completed(ctx.m1, "M5")
    m15 = resample_completed(ctx.m1, "M15")
    m30 = resample_completed(ctx.m1, "M30")
    h1 = resample_completed(ctx.m1, "H1")
    h4 = resample_completed(ctx.m1, "H4")
    if h1.empty or m5.empty:
        return PipelineDecision("skip", "multi_timeframe", ["insufficient_htf"])

    regime = classify_regime(h1, pip)
    if regime == "noise":
        return PipelineDecision("skip", "regime", ["no_trade_noise"])

    setups = collect_setups(
        m5=m5, h1=h1, regime=regime, m1=ctx.m1, m15=m15, m30=m30, h4=h4
    )
    independent = {s.source for s in setups}
    if len(independent) < 2:
        return PipelineDecision(
            "skip",
            "confluence",
            [s.reason for s in setups] or ["need_two_independent_setups"],
            extras={"regime": regime},
        )

    stop = float(ctx.stop_pips or 0.0)
    take = float(ctx.take_pips)
    if stop > 0 and take > 0 and (take / stop) <= (1.0 / 20.0):
        return PipelineDecision("skip", "payoff", ["asymmetric_hide_tail"])
    if ctx.modeled_expectancy is not None and float(ctx.modeled_expectancy) <= 0:
        return PipelineDecision("skip", "payoff", ["modeled_e_nonpositive"])

    reasons = [s.reason for s in setups]
    reasons.append(f"regime:{regime}")
    return PipelineDecision(
        "candidate",
        "execution",
        reasons,
        extras={"regime": regime, "sources": sorted(independent)},
    )
