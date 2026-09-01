"""Shadow comparison of Old Firehose vs Intelligent Firehose. Never places orders."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

from aegis.engines import PositionSnapshot
from aegis.intel.strategy_model import ValidatedStrategyModel
from aegis.intel.thesis_fire import ThesisFireDecision, evaluate_thesis_fire
from aegis.portfolio_risk import portfolio_pretrade_decision


def old_firehose_side(signal_side: str | None) -> str:
    if signal_side in {"buy", "sell"}:
        return signal_side
    return "skip"


def compare_bar(
    *,
    symbol: str,
    bar_time: str,
    old_side: str | None,
    new_decision: ThesisFireDecision,
) -> dict[str, Any]:
    """Join one completed bar. Same symbol and timestamp for both brains."""
    return {
        "schema": "firehose_vs_firehose.v1",
        "placed_orders": False,
        "symbol": str(symbol),
        "bar_time": str(bar_time),
        "old": {"action": old_firehose_side(old_side)},
        "new": {
            "action": new_decision.action,
            "reason": new_decision.reason,
            "expected_net_value": new_decision.expected_net_value,
        },
    }


def aligned_shadow_rows(
    old_rows: Sequence[Mapping[str, Any]],
    new_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Require identical (symbol, bar_time) keys; refuse mixed windows."""
    old_map = {(str(row["symbol"]), str(row["bar_time"])): row for row in old_rows}
    new_map = {(str(row["symbol"]), str(row["bar_time"])): row for row in new_rows}
    if set(old_map) != set(new_map):
        raise ValueError("old and new firehose rows must share the same symbol/bar_time set")
    out: list[dict[str, Any]] = []
    for key in sorted(old_map):
        old = old_map[key]
        new = new_map[key]
        out.append(
            compare_bar(
                symbol=key[0],
                bar_time=key[1],
                old_side=old.get("side"),
                new_decision=ThesisFireDecision(
                    action=str(new.get("action") or "skip"),
                    reason=str(new.get("reason") or ""),
                    expected_net_value=new.get("expected_net_value"),
                ),
            )
        )
    return out


def summarize_shadow_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    old_actions = Counter(str((row.get("old") or {}).get("action") or "skip") for row in rows)
    new_actions = Counter(str((row.get("new") or {}).get("action") or "skip") for row in rows)
    disagreements = 0
    for row in rows:
        old = str((row.get("old") or {}).get("action") or "skip")
        new = str((row.get("new") or {}).get("action") or "skip")
        old_trade = old in {"buy", "sell"}
        new_trade = new in {"fire", "scale"}
        if old_trade != new_trade:
            disagreements += 1
    reasons = Counter(str((row.get("new") or {}).get("reason") or "") for row in rows)
    return {
        "bars_compared": len(rows),
        "placed_orders": any(bool(row.get("placed_orders")) for row in rows),
        "old_actions": dict(old_actions),
        "new_actions": dict(new_actions),
        "old_proposed_trades": old_actions.get("buy", 0) + old_actions.get("sell", 0),
        "new_proposed_fires": new_actions.get("fire", 0),
        "new_proposed_scales": new_actions.get("scale", 0),
        "new_proposed_reduces": new_actions.get("reduce", 0),
        "new_proposed_exits": new_actions.get("exit", 0),
        "new_skips": new_actions.get("skip", 0),
        "disagreements": disagreements,
        "top_new_reasons": reasons.most_common(8),
    }


def scoreboard_markdown(rows: Sequence[Mapping[str, Any]]) -> str:
    stats = summarize_shadow_rows(rows)
    reason_lines = [
        f"- `{reason or 'unspecified'}`: {count}" for reason, count in stats["top_new_reasons"]
    ] or ["- none"]
    return "\n".join(
        [
            "# Firehose vs Firehose (shadow)",
            "",
            "placed_orders: false",
            f"bars_compared: {stats['bars_compared']}",
            f"old_proposed_trades: {stats['old_proposed_trades']}",
            f"new_proposed_fires: {stats['new_proposed_fires']}",
            f"new_proposed_scales: {stats['new_proposed_scales']}",
            f"new_proposed_reduces: {stats['new_proposed_reduces']}",
            f"new_proposed_exits: {stats['new_proposed_exits']}",
            f"new_skips: {stats['new_skips']}",
            f"disagreements: {stats['disagreements']}",
            "",
            "Old Firehose actions: " + ", ".join(
                f"{key}={value}" for key, value in sorted(stats["old_actions"].items())
            ),
            "Intelligent Firehose actions: " + ", ".join(
                f"{key}={value}" for key, value in sorted(stats["new_actions"].items())
            ),
            "",
            "Top Intelligent reasons:",
            *reason_lines,
            "",
            "The intelligent firehose does not win by trading less. It wins only if",
            "later sealed evidence shows better expectancy, payoff, and tail risk.",
            "",
        ]
    )


def shadow_thesis_decision(
    *,
    strategy: ValidatedStrategyModel | None,
    state_expected_net_value: float | None,
    analogue_n: int,
    analogue_n_losses: int,
    uncertainty: str,
    eligible: bool,
    positions: Iterable[PositionSnapshot] = (),
    symbol: str = "EURUSD",
    side: str = "buy",
    quantity: float = 0.01,
    avg_price: float = 1.0,
    portfolio_cfg: Mapping[str, Any] | None = None,
) -> ThesisFireDecision:
    """Runtime thesis fire using inherited strategy + portfolio library. No broker calls."""
    ok, reason, _event = portfolio_pretrade_decision(
        positions=list(positions),
        symbol=symbol,
        side=side,
        quantity=quantity,
        avg_price=avg_price,
        cfg=dict(portfolio_cfg or {"max_positions": 40, "max_currency_direction_positions": 0}),
    )
    return evaluate_thesis_fire(
        strategy=strategy,
        state_expected_net_value=state_expected_net_value,
        analogue_n=analogue_n,
        analogue_n_losses=analogue_n_losses,
        uncertainty=uncertainty,
        eligible=eligible,
        portfolio_ok=ok,
        portfolio_reason=reason,
    )
