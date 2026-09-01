#!/usr/bin/env python3
"""Run a read-only intelligence shadow cycle; it never sends an order."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.config import load_config  # noqa: E402
from aegis.engines import create_engine  # noqa: E402
from aegis.backtest import run_backtest  # noqa: E402
from aegis.research.books_index import BookIndex  # noqa: E402
from aegis.research.baseline import firehose_benchmark_config  # noqa: E402
from aegis.research.costs import cost_book_from_deals  # noqa: E402
from aegis.research.entry_signals import entry_families  # noqa: E402
from aegis.research.intelligence_cycle import (  # noqa: E402
    intelligence_cycle_markdown,
    run_intelligence_cycle,
)
from aegis.research.market_state import build_market_state  # noqa: E402
from aegis.research.market_state_history import (  # noqa: E402
    current_state_signature,
    validate_state_matched_challengers,
)
from aegis.research.portfolio import portfolio_state  # noqa: E402
from aegis.research.registry import ExperimentRegistry  # noqa: E402


def _deal_outcomes(path: Path, *, symbol: str) -> list[float]:
    by_ticket: dict[str, dict] = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(row, dict)
            and row.get("source") == "mt5_deal"
            and row.get("ticket")
            and str(row.get("symbol") or "").upper() == str(symbol).upper()
        ):
            by_ticket[str(row["ticket"])] = row
    out = []
    for row in by_ticket.values():
        try:
            out.append(float(row["pnl"]))
        except (KeyError, TypeError, ValueError):
            pass
    return out


def _readonly_m1(cfg: dict, symbol: str, days: int) -> tuple[pd.DataFrame, dict, dict]:
    engine = create_engine({**cfg, "allow_live": False})
    if not hasattr(engine, "connect_readonly"):
        raise RuntimeError("engine lacks read-only attach")
    engine.connect_readonly()
    bars = engine.bars(symbol, "1m", int(days))
    frame = pd.DataFrame(
        [
            {
                "time": bar.time,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
    )
    positions = [
        {
            "symbol": pos.symbol,
            "side": pos.side,
            "quantity": pos.quantity,
            "ticket": pos.ticket,
            "unrealized_pnl": pos.unrealized_pnl,
        }
        for pos in engine.positions()
    ]
    return frame, portfolio_state(positions), {"source": "mt5_readonly", "open_positions": len(positions)}


def _state_matched_validation(
    m1: pd.DataFrame,
    cfg: dict,
    *,
    symbol: str,
    side: str,
    candidate: str,
) -> dict:
    state = build_market_state(
        symbol=symbol,
        m1=m1,
        provenance={"source": "historical_mt5_completed_bars"},
    )
    candidates = {}
    research_cfg = firehose_benchmark_config()
    research_cfg["symbol"] = symbol
    for key in (
        "spread_bps",
        "slippage_bps",
        "commission_bps",
        "commission_round_trip_usd",
        "risk_percent",
        "starting_equity",
        "session_start_utc",
        "session_end_utc",
        "entry_rr",
        "entry_atr_stop_mult",
        "pullback_rr",
        "pullback_swing_bars",
        "pullback_trend_ema",
        "pullback_touch_bars",
        "pullback_min_stop_pips",
    ):
        if key in cfg:
            research_cfg[key] = cfg[key]
    research_cfg.update(
        {
            "allow_live": False,
            "intel_enabled": False,
            "ntz_max_trades_day": 0,
            "ntz_flatten_utc": None,
            "pyramid_enabled": False,
        }
    )
    prepare_fn, signal_fn = entry_families()[candidate]
    candidates[candidate] = run_backtest(
        m1,
        research_cfg,
        prepare_fn=prepare_fn,
        signal_fn=signal_fn,
    ).trades
    return validate_state_matched_challengers(
        candidates,
        signature=current_state_signature(state, side),
    )


def _validation_markdown(validation: dict) -> str:
    hold = validation.get("sealed_holdout") or {}
    search = validation.get("train_search") or []
    matched = sum(int(row.get("matched") or 0) for row in search)
    return "\n".join(
        [
            "",
            "## State-matched challenger validation",
            "",
            f"- Selected on purged training data: `{validation.get('selected') or 'none'}`",
            f"- Sealed decision: `{validation.get('decision')}`",
            f"- Reason: {validation.get('reason')}",
            f"- Searches corrected for: {validation.get('n_searches', 0)}",
            f"- Point-in-time state matches: {matched}",
            f"- Sealed trades: {hold.get('n_trades', 0)}",
            f"- Sealed expectancy (R): {hold.get('expectancy')}",
            f"- Sealed profit factor: {hold.get('profit_factor')}",
            f"- Train/hold boundary: {validation.get('train_max')} < {validation.get('holdout_min')}",
            "- Promotion: live YAML and CORE remain unchanged unless every governed gate passes.",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Research-only MarketState/thesis cycle")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", required=True, choices=("buy", "sell"))
    parser.add_argument("--setup", required=True)
    parser.add_argument("--book-query", required=True)
    parser.add_argument("--invalidation", required=True)
    parser.add_argument("--duration", default="unknown")
    parser.add_argument("--candidate", required=True, choices=tuple(entry_families()))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--deals", type=Path, default=BOT / "optimizer" / "metrics" / "trades.jsonl")
    parser.add_argument("--config", type=Path, default=BOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--report", type=Path, default=BOT / "reports" / "research" / "intelligence_cycle.md")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.csv:
        m1 = pd.read_csv(args.csv)
        portfolio, execution = {}, {"source": "csv"}
    else:
        m1, portfolio, execution = _readonly_m1(cfg, args.symbol, args.days)
    if len(m1) < 300:
        raise SystemExit(f"only {len(m1)} M1 bars; refusing intelligence cycle")
    validation = _state_matched_validation(
        m1,
        cfg,
        symbol=args.symbol.upper(),
        side=args.side,
        candidate=args.candidate,
    )
    outcomes = list(validation.get("sealed_outcomes") or [])
    outcome_scope = "state_matched"
    if not outcomes:
        outcomes = _deal_outcomes(args.deals, symbol=args.symbol)
        outcome_scope = "symbol_only"
    if not outcomes:
        raise SystemExit("no state-matched or ticket-deduped outcomes available")
    index = BookIndex()
    if not index.path.is_file():
        raise SystemExit("book index missing; run research_book_audit.py first")
    thesis_id = (
        f"{args.symbol.upper()}_{args.side.upper()}_{args.setup.upper().replace(' ', '_')}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    result = run_intelligence_cycle(
        thesis_id=thesis_id,
        symbol=args.symbol.upper(),
        side=args.side,
        setup=args.setup,
        m1=m1,
        historical_outcomes=outcomes,
        book_query=args.book_query,
        invalidation=args.invalidation,
        expected_duration=args.duration,
        outcome_scope=outcome_scope,
        index=index,
        registry=ExperimentRegistry(),
        execution={**execution, "deals": cost_book_from_deals(args.deals)},
        portfolio=portfolio,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        intelligence_cycle_markdown(result) + _validation_markdown(validation),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "report": str(args.report),
                "thesis_id": thesis_id,
                "decision": result["exposure"]["action"],
                "challenger": validation.get("selected"),
                "challenger_validation": validation.get("decision"),
                "challenger_reason": validation.get("reason"),
                "outcome_scope": outcome_scope,
                "recorded": result["recorded"],
                "mt5_touched": False,
                "placed_orders": False,
                "promoted_live_yaml": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
