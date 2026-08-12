#!/usr/bin/env python3
"""Chronological MGC firehose search and promotion report."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from math import inf, isfinite
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402
from aegis.mgc_firehose import (  # noqa: E402
    CandidateScore,
    MomentumParams,
    QuoteTick,
    RegimeFlowParams,
    ReplaySummary,
    SecondQuote,
    aggregate_second_quotes,
    replay_regime_flow,
    select_candidate,
    wilson_lower_bound,
)


@dataclass(frozen=True)
class SampleReadiness:
    ready: bool
    session_count: int
    usable_records: int
    halt_reason: str


@dataclass(frozen=True)
class PromotionDecision:
    promoted: bool
    halt_reason: str


@dataclass(frozen=True)
class CandidateEvaluation:
    params: RegimeFlowParams
    score: CandidateScore
    development: ReplaySummary
    validation: ReplaySummary


def sample_readiness(*, session_count: int, usable_records: int) -> SampleReadiness:
    ready = session_count >= 10 and usable_records >= 250_000
    return SampleReadiness(
        ready=ready,
        session_count=session_count,
        usable_records=usable_records,
        halt_reason="ready for chronological search"
        if ready
        else "collecting ten-session broker-native sample",
    )


def chronological_partitions(records):
    """Freeze the first ten sessions as 6 development, 2 validation, 2 holdout."""
    ordered = sorted(records, key=lambda record: record.time)
    sessions = sorted({record.time.date() for record in ordered})
    if len(sessions) < 10:
        raise ValueError("ten chronological sessions are required")
    chosen = sessions[:10]
    development_dates = set(chosen[:6])
    validation_dates = set(chosen[6:8])
    holdout_dates = set(chosen[8:10])
    return (
        [record for record in ordered if record.time.date() in development_dates],
        [record for record in ordered if record.time.date() in validation_dates],
        [record for record in ordered if record.time.date() in holdout_dates],
    )


def promotion_decision(
    primary: ReplaySummary,
    stressed: ReplaySummary,
    *,
    hourly_pnl: list[float],
) -> PromotionDecision:
    """Apply frozen-holdout statistical, cost, and concentration gates."""
    if primary.trades < 500:
        return PromotionDecision(False, "holdout has fewer than 500 trades")
    if primary.net_dollars_per_trade <= 0 or primary.expectancy_r <= 0:
        return PromotionDecision(False, "holdout expectancy is not positive")
    if primary.profit_factor < 1.15:
        return PromotionDecision(False, "holdout profit factor is below 1.15")
    if primary.max_drawdown_pct >= 3.0:
        return PromotionDecision(False, "holdout maximum drawdown reached 3%")
    if stressed.net_dollars_per_trade <= 0:
        return PromotionDecision(False, "two-tick slippage stress is not positive")
    wins = int(round(primary.trades * primary.win_rate / 100.0))
    if wilson_lower_bound(wins, primary.trades) <= 0.50:
        return PromotionDecision(False, "95% win-rate lower bound is not above 50%")
    positive_hours = [value for value in hourly_pnl if value > 0]
    positive_total = sum(positive_hours)
    if positive_total <= 0:
        return PromotionDecision(False, "holdout has no positive trading hours")
    if max(positive_hours) / positive_total > 0.35:
        return PromotionDecision(False, "one hour contributes more than 35% of positive P&L")
    return PromotionDecision(True, "all frozen-holdout promotion gates passed")


def candidate_grid() -> list[RegimeFlowParams]:
    """Return a bounded, deterministic family of cost-viable flow scalpers."""
    window_pairs = ((5, 3), (10, 5), (20, 10))
    efficiencies = (0.50, 0.70)
    target_stops = ((8, 6), (12, 8), (16, 10))
    hold_seconds = (10, 20)
    flow_gates = (
        (0.00, 0.00, 0.00, 4.0),
        (0.10, 0.05, 0.00, 3.0),
        (0.20, 0.10, 0.10, 2.0),
    )
    candidates: list[RegimeFlowParams] = []
    for (lookback, breakout), efficiency, (target, stop), hold, gates in product(
        window_pairs,
        efficiencies,
        target_stops,
        hold_seconds,
        flow_gates,
    ):
        book, microprice, trade_flow, max_spread = gates
        candidates.append(
            RegimeFlowParams(
                momentum=MomentumParams(
                    lookback_seconds=lookback,
                    breakout_seconds=breakout,
                    min_efficiency=efficiency,
                    target_ticks=target,
                    stop_ticks=stop,
                    max_hold_seconds=hold,
                    cooldown_seconds=1,
                ),
                min_book_imbalance=book,
                min_microprice_bias_ticks=microprice,
                min_trade_flow_imbalance=trade_flow,
                max_spread_ticks=max_spread,
            )
        )
    return candidates


def _profit_factor(values: list[float]) -> float:
    profit = sum(value for value in values if value > 0)
    loss = abs(sum(value for value in values if value < 0))
    if loss > 0:
        return profit / loss
    return inf if profit > 0 else 0.0


def candidate_score(
    name: str,
    development: ReplaySummary,
    validation: ReplaySummary,
) -> CandidateScore:
    """Map executable replays into the maximum-WR selector contract."""
    by_session: dict[object, list[float]] = {}
    for trade in (*development.results, *validation.results):
        by_session.setdefault(trade.entry_time.date(), []).append(trade.net_pnl_usd)
    if by_session:
        worst_session_pf = min(_profit_factor(values) for values in by_session.values())
    else:
        worst_session_pf = min(development.profit_factor, validation.profit_factor)
    return CandidateScore(
        name=name,
        dev_expectancy=development.expectancy_r,
        validation_expectancy=validation.expectancy_r,
        dev_profit_factor=development.profit_factor,
        validation_profit_factor=validation.profit_factor,
        worst_session_profit_factor=worst_session_pf,
        max_drawdown_pct=max(development.max_drawdown_pct, validation.max_drawdown_pct),
        trades_per_day=validation.trades_per_day,
        validation_wins=int(round(validation.trades * validation.win_rate / 100.0)),
        validation_trades=validation.trades,
    )


def params_name(params: RegimeFlowParams) -> str:
    momentum = params.momentum
    return (
        f"lb{momentum.lookback_seconds}_bo{momentum.breakout_seconds}_"
        f"eff{momentum.min_efficiency:.2f}_tp{momentum.target_ticks}_"
        f"sl{momentum.stop_ticks}_hold{momentum.max_hold_seconds}_"
        f"book{params.min_book_imbalance:.2f}_micro{params.min_microprice_bias_ticks:.2f}_"
        f"flow{params.min_trade_flow_imbalance:.2f}_spread{params.max_spread_ticks:.0f}"
    )


def params_from_config(cfg: dict) -> RegimeFlowParams:
    return RegimeFlowParams(
        momentum=MomentumParams(
            lookback_seconds=int(cfg.get("mgc_lookback_seconds", 10)),
            breakout_seconds=int(cfg.get("mgc_breakout_seconds", 5)),
            min_efficiency=float(cfg.get("mgc_min_efficiency", 0.50)),
            target_ticks=int(cfg.get("mgc_target_ticks", 8)),
            stop_ticks=int(cfg.get("mgc_stop_ticks", 6)),
            max_hold_seconds=int(cfg.get("mgc_max_hold_seconds", 10)),
            cooldown_seconds=int(cfg.get("mgc_cooldown_seconds", 1)),
        ),
        min_book_imbalance=float(cfg.get("mgc_min_book_imbalance", 0.0)),
        min_microprice_bias_ticks=float(cfg.get("mgc_min_microprice_bias_ticks", 0.0)),
        min_trade_flow_imbalance=float(cfg.get("mgc_min_trade_flow_imbalance", 0.0)),
        max_spread_ticks=float(cfg.get("max_spread_ticks", 4.0)),
    )


def replay(records: list[SecondQuote], params: RegimeFlowParams, cfg: dict, slippage: float) -> ReplaySummary:
    return replay_regime_flow(
        records,
        params=params,
        quantity=float(cfg.get("order_quantity", 1)),
        multiplier=float(cfg.get("contract_multiplier", 10)),
        tick_size=float(cfg.get("tick_size", 0.1)),
        fixed_round_trip_usd=float(cfg.get("ib_round_trip_commission_usd", 1.92)),
        slippage_ticks=slippage,
        starting_equity=float(cfg.get("starting_equity", 250_000.0)),
    )


def search_candidates(
    development: list[SecondQuote],
    validation: list[SecondQuote],
    cfg: dict,
) -> tuple[CandidateEvaluation | None, list[CandidateEvaluation]]:
    evaluations: list[CandidateEvaluation] = []
    for params in candidate_grid():
        development_summary = replay(development, params, cfg, slippage=1.0)
        validation_summary = replay(validation, params, cfg, slippage=1.0)
        name = params_name(params)
        score = candidate_score(name, development_summary, validation_summary)
        evaluations.append(
            CandidateEvaluation(params, score, development_summary, validation_summary)
        )
    winner_score = select_candidate([evaluation.score for evaluation in evaluations])
    if winner_score is None:
        return None, evaluations
    winner = next(evaluation for evaluation in evaluations if evaluation.score == winner_score)
    return winner, evaluations


def hourly_pnl(summary: ReplaySummary) -> list[float]:
    totals: dict[tuple[object, int], float] = {}
    for trade in summary.results:
        key = (trade.entry_time.date(), trade.entry_time.hour)
        totals[key] = totals.get(key, 0.0) + trade.net_pnl_usd
    return list(totals.values())


def _metric(value: float, digits: int = 2) -> str:
    if not isfinite(value):
        return "inf"
    return f"{value:.{digits}f}"


def _summary_rows(summary: ReplaySummary) -> str:
    wins = int(round(summary.trades * summary.win_rate / 100.0))
    lower = wilson_lower_bound(wins, summary.trades) * 100.0 if summary.trades else 0.0
    return f"""| Closed trades | {summary.trades:,} |
| Trades/day | {_metric(summary.trades_per_day)} |
| Win rate | {_metric(summary.win_rate)}% |
| WR 95% lower bound | {_metric(lower)}% |
| E[R] | {_metric(summary.expectancy_r, 4)} |
| Net dollars/trade | ${_metric(summary.net_dollars_per_trade, 4)} |
| Profit factor | {_metric(summary.profit_factor)} |
| Maximum drawdown | {_metric(summary.max_drawdown_pct)}% |
| Start equity | ${_metric(summary.start_equity)} |
| End equity | ${_metric(summary.end_equity)} |
| Net P&L | ${_metric(summary.net_pnl_usd)} |
| Modeled fixed/slippage costs | ${_metric(summary.total_cost_usd)} |"""


def load_seconds(path: Path) -> list[SecondQuote]:
    if not path.exists():
        return []
    out: list[SecondQuote] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        payload["time"] = datetime.fromisoformat(str(payload["time"]).replace("Z", "+00:00"))
        out.append(SecondQuote(**payload))
    return sorted(out, key=lambda record: record.time)


def load_tick_seconds(
    path: Path,
    *,
    tick_size: float,
    max_spread_ticks: float,
) -> list[SecondQuote]:
    """Rebuild flow-aware seconds from the append-only raw event capture."""
    if not path.exists():
        return []
    ticks: list[QuoteTick] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        payload["time"] = datetime.fromisoformat(str(payload["time"]).replace("Z", "+00:00"))
        ticks.append(QuoteTick(**payload))
    return aggregate_second_quotes(
        ticks,
        tick_size=tick_size,
        max_spread_ticks=max_spread_ticks,
    )


def write_insufficient_report(
    path: Path,
    *,
    records: list[SecondQuote],
    readiness: SampleReadiness,
    cfg: dict,
) -> None:
    start = records[0].time.isoformat() if records else "unavailable"
    end = records[-1].time.isoformat() if records else "unavailable"
    total = len(records)
    diagnostic = replay(
        records,
        params_from_config(cfg),
        cfg,
        slippage=float(cfg.get("slippage_ticks", 1)),
    ) if records else ReplaySummary((), 0, 0, 0, 0, 0, 0, 0, float(cfg.get("starting_equity", 250_000)), float(cfg.get("starting_equity", 250_000)), 0, 0, "no_data")
    text = f"""# MGC Validated Maximum-WR Firehose

## Current measured state

| Metric | Result |
|---|---:|
| Contract | `{cfg.get('ib_futures_expiry', 'unavailable')}` MGC, COMEX |
| Sample window | {start} to {end} |
| One-second records | {total:,} |
| Usable records | {readiness.usable_records:,} |
| Trading sessions | {readiness.session_count} |
{_summary_rows(diagnostic)}
| Paper promoted | **false** |
| Halt reason | **{readiness.halt_reason}** |

These are diagnostic in-sample results on delayed/sparse data, not promotion evidence.
Observed bid/ask prices, `$1.92` fixed round-trip fees, and configured slippage are included.
No orders are sent while the ten-session live-data sample is insufficient.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_search_report(
    path: Path,
    *,
    records: list[SecondQuote],
    winner: CandidateEvaluation | None,
    evaluated: int,
    holdout: ReplaySummary | None,
    stressed: ReplaySummary | None,
    decision: PromotionDecision,
    cfg: dict,
) -> None:
    start = records[0].time.isoformat()
    end = records[-1].time.isoformat()
    if winner is None or holdout is None or stressed is None:
        selected = "none"
        metrics = "| Closed trades | 0 |"
        stress_net = "unavailable"
    else:
        selected = params_name(winner.params)
        metrics = _summary_rows(holdout)
        stress_net = f"${_metric(stressed.net_dollars_per_trade, 4)}"
    text = f"""# MGC Validated Maximum-WR Firehose

## Frozen holdout result

| Metric | Result |
|---|---:|
| Contract | `{cfg.get('ib_futures_expiry', 'unavailable')}` MGC, COMEX |
| Sample window | {start} to {end} |
| Candidate models evaluated | {evaluated} |
| Selected model | `{selected}` |
{metrics}
| Two-tick stress net/trade | {stress_net} |
| Paper promoted | **{str(decision.promoted).lower()}** |
| Halt reason | **{decision.halt_reason}** |

Selection used six development sessions and two validation sessions. The final two
sessions were opened once for this report. Frequency never overrides expectancy,
cost, confidence, concentration, or drawdown gates. A measured 100% sample is not
a guarantee of the next trade.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune the MGC cost-gated firehose")
    parser.add_argument("--config", default=str(ROOT / "config_ib_paper_mgc_shadow.yaml"))
    args = parser.parse_args()
    cfg = load_config(args.config)
    tick_records = load_tick_seconds(
        ROOT / "reports" / "mgc_ticks.jsonl",
        tick_size=float(cfg.get("tick_size", 0.1)),
        max_spread_ticks=float(cfg.get("max_spread_ticks", 4.0)),
    )
    records = tick_records or load_seconds(ROOT / "reports" / "mgc_seconds.jsonl")
    usable = sum(record.usable for record in records)
    sessions = len({record.time.date() for record in records if record.usable})
    readiness = sample_readiness(session_count=sessions, usable_records=usable)
    report = ROOT / "reports" / "MGC_FIREHOSE.md"
    if not readiness.ready:
        write_insufficient_report(report, records=records, readiness=readiness, cfg=cfg)
        print(f"paper_promoted=false; {readiness.halt_reason}; report={report}")
        return
    development, validation, holdout_records = chronological_partitions(records)
    winner, evaluations = search_candidates(development, validation, cfg)
    if winner is None:
        decision = PromotionDecision(False, "no development/validation candidate passed")
        write_search_report(
            report,
            records=records,
            winner=None,
            evaluated=len(evaluations),
            holdout=None,
            stressed=None,
            decision=decision,
            cfg=cfg,
        )
        print(f"paper_promoted=false; {decision.halt_reason}; report={report}")
        return
    holdout = replay(holdout_records, winner.params, cfg, slippage=1.0)
    stressed = replay(holdout_records, winner.params, cfg, slippage=2.0)
    decision = promotion_decision(holdout, stressed, hourly_pnl=hourly_pnl(holdout))
    write_search_report(
        report,
        records=records,
        winner=winner,
        evaluated=len(evaluations),
        holdout=holdout,
        stressed=stressed,
        decision=decision,
        cfg=cfg,
    )
    print(
        f"paper_promoted={str(decision.promoted).lower()}; "
        f"{decision.halt_reason}; report={report}"
    )


if __name__ == "__main__":
    main()
