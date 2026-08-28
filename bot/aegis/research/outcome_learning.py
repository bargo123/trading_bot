"""Outcome-learning consumer for the Intelligent Firehose.

Reads `intel/outcome_log.jsonl` (write-only until now) and turns reconciled
exits into structured evidence: scoreboard metrics, payoff geometry, and
per-dimension slices. It observes; it never places orders and never mutates
trading state.
"""
from __future__ import annotations

import json
import hashlib
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aegis.intel.expected_value import payoff_metrics
from aegis.research.costs import pnl_summary
from aegis.research.registry import DuplicateExperimentError, ExperimentRegistry
from aegis.research_factory.evaluation import record_outcome

DEFAULT_OUTCOME_PATH = Path(__file__).resolve().parents[2] / "intel" / "outcome_log.jsonl"


def _broker_confirmed(row: Mapping[str, Any]) -> bool:
    facts = row.get("broker_facts")
    return (
        str(row.get("evidence_status") or "") == "BROKER_CONFIRMED"
        or row.get("broker_confirmed") is True
        or (
            isinstance(facts, Mapping)
            and (
                facts.get("confirmed") is True
                or str(facts.get("status") or "") == "BROKER_CONFIRMED"
            )
        )
    )


def _broker_position_side(row: Mapping[str, Any]) -> str | None:
    facts = row.get("broker_facts")
    candidates = (
        row.get("position_side"),
        facts.get("position_side") if isinstance(facts, Mapping) else None,
    )
    for candidate in candidates:
        side = str(candidate or "").strip().lower()
        if side in {"buy", "sell"}:
            return side
    return None


def _normalize_broker_exit_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    """Keep closing-DEAL action from becoming the original position side."""
    normalized = dict(row)
    if normalized.get("is_exit") and _broker_confirmed(normalized):
        normalized["side"] = _broker_position_side(normalized) or "unknown"
    return normalized


def _broker_truth_pnl(row: Mapping[str, Any]) -> float | None:
    """Prefer confirmed realized net PnL; event PnL is only a fallback."""
    value = None
    if _broker_confirmed(row):
        value = row.get("realized_net_usd")
        if value is None:
            facts = row.get("broker_facts")
            if isinstance(facts, Mapping):
                value = facts.get("realized_net_usd")
    if value is None:
        value = row.get("pnl")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def read_outcomes(path: Path | None = None) -> list[dict[str, Any]]:
    """Read and deduplicate outcome rows by ticket identity.

    Reconciliation writes one row per deal ticket. A duplicated row (e.g. from
    a cursor reset) must not double-count PnL, so we keep the first occurrence.
    """
    target = Path(path) if path is not None else DEFAULT_OUTCOME_PATH
    if not target.is_file():
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        payload = _normalize_broker_exit_identity(payload)
        ticket = str(payload.get("ticket") or "")
        if ticket and ticket != "0":
            if ticket in seen:
                continue
            seen.add(ticket)
        rows.append(payload)
    return rows


def exit_pnls(rows: Iterable[Mapping[str, Any]]) -> list[float]:
    out: list[float] = []
    for row in rows:
        if not row.get("is_exit"):
            continue
        pnl = _broker_truth_pnl(row)
        if pnl is not None:
            out.append(pnl)
    return out


def slice_learning(
    rows: Iterable[Mapping[str, Any]],
    *,
    by: tuple[str, ...] = ("symbol", "side", "close_reason"),
) -> list[dict[str, Any]]:
    """Slice exit PnL by context dimensions; ranked by net PnL."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if not row.get("is_exit"):
            continue
        pnl = _broker_truth_pnl(row)
        if pnl is None:
            continue
        key = "|".join(str(row.get(field) or "unknown") for field in by)
        buckets[key].append(pnl)
    ranked = sorted(
        (
            {"key": key, "by": list(by), **payoff_metrics(values)}
            for key, values in buckets.items()
            if len(values) >= 5
        ),
        key=lambda item: float(item.get("expectancy") or -1e18),
        reverse=True,
    )
    return ranked


def summarize_outcomes(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Full learning summary over reconciled exit rows."""
    rows = list(rows)
    exits = [row for row in rows if row.get("is_exit")]
    pnls = exit_pnls(exits)
    metrics = payoff_metrics(pnls)
    by_symbol = slice_learning(exits, by=("symbol",))
    by_side = slice_learning(exits, by=("side",))
    by_reason = slice_learning(exits, by=("close_reason",))
    by_symbol_side = slice_learning(exits, by=("symbol", "side"))
    return {
        "schema": "outcome_learning.v1",
        "label": "research_proxy",
        "n_rows": len(rows),
        "n_exits": len(exits),
        "metrics": metrics,
        "by_symbol": by_symbol,
        "by_side": by_side,
        "by_close_reason": by_reason,
        "by_symbol_side": by_symbol_side,
    }


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _event_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _median(values: Iterable[float]) -> float | None:
    items = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not items:
        return None
    middle = len(items) // 2
    if len(items) % 2:
        return items[middle]
    return (items[middle - 1] + items[middle]) / 2.0


def _trade_state_path(
    trace_pnls: list[tuple[Mapping[str, Any], float | None]],
    final_pnl: float,
) -> list[str]:
    """Compress observed executable PnL into an auditable lifecycle path."""
    path = ["OPEN"]
    values = [value for _event, value in trace_pnls if value is not None]
    peak_index = max(range(len(values)), key=values.__getitem__) if values else None
    seen_green = False
    value_index = -1
    for _event, value in trace_pnls:
        if value is None:
            continue
        value_index += 1
        if value > 0:
            if not seen_green:
                path.append("GREEN")
                seen_green = True
            if value_index == peak_index and (not path or path[-1] != "PEAK"):
                path.append("PEAK")
        elif seen_green:
            if "GREEN_TO_RED" not in path:
                path.append("GREEN_TO_RED")
        elif "RED" not in path:
            path.append("RED")
    path.append("CLOSE_WIN" if final_pnl > 0 else "CLOSE_LOSS" if final_pnl < 0 else "CLOSE_FLAT")
    return path


def summarize_fast_trade_autopsy(
    outcomes: Iterable[Mapping[str, Any]],
    journal_events: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Join broker exits to runtime traces and classify only observed causes.

    Missing trace facts remain ``None`` and become ``UNCLASSIFIED_LOSS`` rather
    than being guessed.  This is an observation report, not a promotion gate.
    """
    trades: list[dict[str, Any]] = []
    for outcome in outcomes:
        if not outcome.get("is_exit"):
            continue
        ticket = str(outcome.get("ticket") or "").strip()
        pnl = _broker_truth_pnl(outcome)
        if not ticket or pnl is None:
            continue
        position = str(outcome.get("position") or "").strip()
        event_groups = [journal_events.get(ticket) or []]
        if position and position != ticket:
            event_groups.append(journal_events.get(position) or [])
        events = [dict(event) for group in event_groups for event in group]
        events.sort(
            key=lambda event: _event_time(event.get("timestamp"))
            or datetime.min.replace(tzinfo=timezone.utc)
        )
        opens = [event for event in events if event.get("event") == "firehose_open"]
        closes = [
            event for event in events
            if event.get("event") == "firehose_close" and event.get("confirmed") is True
        ]
        traces = [event for event in events if event.get("event") == "firehose_exit_trace"]
        pm_exits = [event for event in events if event.get("event") == "pm_exit"]
        opened_at = _event_time(opens[0].get("timestamp")) if opens else None
        closed_at = _event_time(closes[-1].get("timestamp")) if closes else None
        if closed_at is None:
            closed_at = _event_time(outcome.get("time")) or _event_time(outcome.get("ts_utc"))
        hold_s = (
            (closed_at - opened_at).total_seconds()
            if opened_at is not None and closed_at is not None
            else None
        )
        trace_pnls = [
            (event, _finite_number(event.get("pnl_usd")))
            for event in traces
        ]
        trace_values = [value for _event, value in trace_pnls if value is not None]
        peak_executable_pnl_usd = max(trace_values) if trace_values else None
        green_at = next(
            (event_time for event, pnl_usd in trace_pnls
             if pnl_usd is not None and pnl_usd > 0
             for event_time in [_event_time(event.get("timestamp"))]
             if event_time is not None),
            None,
        )
        time_to_green_s = (
            (green_at - opened_at).total_seconds()
            if green_at is not None and opened_at is not None
            else None
        )
        seconds_in_red = 0.0
        for current, following in zip(trace_pnls, trace_pnls[1:]):
            current_time = _event_time(current[0].get("timestamp"))
            next_time = _event_time(following[0].get("timestamp"))
            if current[1] is not None and current[1] <= 0 and current_time and next_time:
                seconds_in_red += max(0.0, (next_time - current_time).total_seconds())
        if trace_pnls and closed_at is not None:
            last_time = _event_time(trace_pnls[-1][0].get("timestamp"))
            if trace_pnls[-1][1] is not None and trace_pnls[-1][1] <= 0 and last_time:
                seconds_in_red += max(0.0, (closed_at - last_time).total_seconds())
        mfe_values = [
            value for event in traces + pm_exits
            for value in [_finite_number(event.get("mfe_usd") or event.get("mfe_before_close"))]
            if value is not None
        ]
        mae_values = [
            value for event in traces + pm_exits
            for value in [_finite_number(event.get("mae_usd") or event.get("mae_before_close"))]
            if value is not None
        ]
        mfe_usd = max(mfe_values) if mfe_values else None
        mae_usd = min(mae_values) if mae_values else None
        exit_reason = str(
            (pm_exits[-1].get("exit_reason") if pm_exits else None)
            or (traces[-1].get("exit_reason") if traces else None)
            or outcome.get("close_reason")
            or outcome.get("reason")
            or "unknown"
        )
        exit_action = str(
            (pm_exits[-1].get("action") if pm_exits else None)
            or (pm_exits[-1].get("exit_action") if pm_exits else None)
            or (traces[-1].get("exit_action") if traces else None)
            or "UNKNOWN"
        )
        reason_lower = exit_reason.lower()
        close_reason = str(outcome.get("close_reason") or "").lower()
        if pnl > 0:
            category = "WINNER_GIVEBACK" if mfe_usd is not None and pnl < mfe_usd else "FAST_CLEAN_WIN"
        elif pnl == 0:
            category = "FLAT_SCRATCH"
        elif mfe_usd is not None and mfe_usd > 0:
            # A losing close after a positive observed excursion is a distinct
            # winner-to-loser failure.  Keep it separate from an ordinary
            # stop/entry loss so Factory can test giveback containment.
            category = "WINNER_GIVEBACK"
        elif any(token in reason_lower for token in ("no_progress", "never_green", "time_decay")):
            category = "NO_PROGRESS"
        elif close_reason == "sl" or "stop" in reason_lower:
            category = "STOP_LOSS"
        elif "spread" in reason_lower:
            category = "SPREAD_COST"
        elif any(token in reason_lower for token in ("regime_change", "regime_changed")):
            category = "REGIME_CHANGE"
        elif any(token in reason_lower for token in ("adverse_selection", "adverse-select")):
            category = "ADVERSE_SELECTION"
        else:
            category = "UNCLASSIFIED_LOSS"
        trades.append(
            {
                "ticket": ticket,
                "symbol": str(outcome.get("symbol") or "unknown"),
                "side": str(outcome.get("side") or "unknown"),
                "pnl": pnl,
                "category": category,
                "exit_reason": exit_reason,
                "exit_action": exit_action,
                "opened_at": opened_at.isoformat() if opened_at is not None else None,
                "closed_at": closed_at.isoformat() if closed_at is not None else None,
                "hold_s": hold_s,
                "time_to_green_s": time_to_green_s,
                "first_net_green_s": time_to_green_s,
                "seconds_in_red_observed_s": seconds_in_red,
                "mfe_usd": mfe_usd,
                "mae_usd": mae_usd,
                "peak_executable_pnl_usd": peak_executable_pnl_usd,
                "giveback_usd": (mfe_usd - pnl if mfe_usd is not None else None),
                "winner_to_loser": bool(
                    peak_executable_pnl_usd is not None
                    and peak_executable_pnl_usd > 0
                    and pnl <= 0
                ),
                "state_path": _trade_state_path(trace_pnls, pnl),
                "evidence_status": "COMPLETE" if opens and closes and (traces or pm_exits) else "PARTIAL",
            }
        )
    pnls = [trade["pnl"] for trade in trades]
    winners = [trade for trade in trades if trade["pnl"] > 0]
    losses = [trade for trade in trades if trade["pnl"] < 0]
    giveback_winners = [trade for trade in winners if trade["category"] == "WINNER_GIVEBACK"]
    loss_category_metrics: dict[str, dict[str, Any]] = {}
    for category, category_losses in sorted(
        ((name, [trade for trade in losses if trade["category"] == name])
         for name in {trade["category"] for trade in losses}),
    ):
        category_pnls = [float(trade["pnl"]) for trade in category_losses]
        loss_category_metrics[category] = {
            "n": len(category_losses),
            "complete_evidence": sum(
                trade["evidence_status"] == "COMPLETE" for trade in category_losses
            ),
            "net_pnl": round(sum(category_pnls), 8),
            "avg_loss": round(sum(category_pnls) / len(category_pnls), 8),
            "median_hold_s": _median(
                trade["hold_s"] for trade in category_losses
                if trade["hold_s"] is not None
            ),
            "median_mfe_usd": _median(
                trade["mfe_usd"] for trade in category_losses
                if trade["mfe_usd"] is not None
            ),
            "median_mae_usd": _median(
                trade["mae_usd"] for trade in category_losses
                if trade["mae_usd"] is not None
            ),
        }
    complete = sum(trade["evidence_status"] == "COMPLETE" for trade in trades)
    with_runtime_trace = sum(
        trade["evidence_status"] == "COMPLETE" or trade["hold_s"] is not None
        for trade in trades
    )
    by_symbol: dict[str, dict[str, Any]] = {}
    for trade in trades:
        bucket = by_symbol.setdefault(trade["symbol"], {"n": 0, "net_pnl": 0.0})
        bucket["n"] += 1
        bucket["net_pnl"] += trade["pnl"]
    for bucket in by_symbol.values():
        bucket["net_pnl"] = round(bucket["net_pnl"], 8)
    return {
        "schema": "fast_trade_autopsy.v1",
        "label": "research_observation",
        "n_trades": len(trades),
        "n_wins": len(winners),
        "n_losses": len(losses),
        "n_with_runtime_trace": with_runtime_trace,
        "n_with_complete_evidence": complete,
        "n_partial_evidence": len(trades) - complete,
        "metrics": payoff_metrics(pnls),
        "median_hold_s": _median(trade["hold_s"] for trade in trades if trade["hold_s"] is not None),
        "median_winning_hold_s": _median(trade["hold_s"] for trade in winners if trade["hold_s"] is not None),
        "median_losing_hold_s": _median(trade["hold_s"] for trade in losses if trade["hold_s"] is not None),
        "median_time_to_green_s": _median(trade["time_to_green_s"] for trade in trades if trade["time_to_green_s"] is not None),
        "seconds_in_red_observed_s": round(sum(trade["seconds_in_red_observed_s"] for trade in trades), 6),
        "median_mfe_usd": _median(trade["mfe_usd"] for trade in trades if trade["mfe_usd"] is not None),
        "median_mae_usd": _median(trade["mae_usd"] for trade in trades if trade["mae_usd"] is not None),
        "winner_giveback_rate": (len(giveback_winners) / len(winners) if winners else None),
        "loss_categories": dict(Counter(trade["category"] for trade in losses)),
        "loss_category_metrics": loss_category_metrics,
        "by_symbol": by_symbol,
        "trades": trades,
        "next_experiments": [
            {
                "category": category,
                "observed_losses": count,
                "status": "PROPOSED_NEEDS_REPLAY",
                "question": f"Can {category.lower()} losses be reduced without lowering positive costed OOS expectancy?",
            }
            for category, count in sorted(Counter(trade["category"] for trade in losses).items())
        ],
    }


def build_daily_trade_behavior_reports(
    summary: Mapping[str, Any],
    *,
    timezone_name: str = "Asia/Amman",
) -> dict[str, dict[str, Any]]:
    """Group broker-confirmed lifecycle observations by local close date."""
    try:
        local_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        local_tz = timezone.utc
        timezone_name = "UTC"
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_trade in summary.get("trades") or []:
        trade = dict(raw_trade)
        closed_at = _event_time(trade.get("closed_at"))
        opened_at = _event_time(trade.get("opened_at"))
        observed_at = closed_at or opened_at
        if observed_at is None:
            continue
        grouped[observed_at.astimezone(local_tz).date().isoformat()].append(trade)

    reports: dict[str, dict[str, Any]] = {}
    for day, trades in sorted(grouped.items()):
        wins = sum(float(trade["pnl"]) > 0 for trade in trades)
        losses = sum(float(trade["pnl"]) < 0 for trade in trades)
        winner_to_loser_count = sum(bool(trade.get("winner_to_loser")) for trade in trades)
        reports[day] = {
            "schema": "daily_trade_behavior.v1",
            "label": "research_observation",
            "date": day,
            "timezone": timezone_name,
            "n_trades": len(trades),
            "n_wins": wins,
            "n_losses": losses,
            "net_pnl_usd": round(sum(float(trade["pnl"]) for trade in trades), 8),
            "winner_to_loser_count": winner_to_loser_count,
            "winner_to_loser_rate": winner_to_loser_count / len(trades) if trades else None,
            "trades": [
                {
                    **trade,
                    "broker_confirmed_net_pnl_usd": trade.get("pnl"),
                }
                for trade in trades
            ],
        }
    return reports


def render_daily_trade_behavior_markdown(report: Mapping[str, Any]) -> str:
    """Render a compact human-readable lifecycle report."""
    lines = [
        f"# Daily Trade Behavior — {report.get('date', 'unknown')}",
        "",
        f"Timezone: {report.get('timezone', 'unknown')}",
        "",
        f"Trades: {report.get('n_trades', 0)} | Wins: {report.get('n_wins', 0)} | "
        f"Losses: {report.get('n_losses', 0)} | Net PnL: ${float(report.get('net_pnl_usd') or 0.0):.4f}",
        "",
        f"Winner-to-loser: {report.get('winner_to_loser_count', 0)}",
        "",
        "| Ticket | Market | Path | Net PnL | First green | Peak | Giveback | Exit |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for trade in report.get("trades") or []:
        path = " -> ".join(str(state) for state in trade.get("state_path") or [])
        first_green = trade.get("first_net_green_s")
        peak = trade.get("peak_executable_pnl_usd")
        giveback = trade.get("giveback_usd")
        exit_text = f"{trade.get('exit_action', 'UNKNOWN')}: {trade.get('exit_reason', 'unknown')}"
        lines.append(
            f"| {trade.get('ticket', '')} | {trade.get('symbol', '')} {trade.get('side', '')} | "
            f"{path} | ${float(trade.get('broker_confirmed_net_pnl_usd') or 0.0):.4f} | "
            f"{'' if first_green is None else f'{float(first_green):.3f}s'} | "
            f"{'' if peak is None else f'${float(peak):.4f}'} | "
            f"{'' if giveback is None else f'${float(giveback):.4f}'} | {exit_text} |"
        )
    return "\n".join(lines) + "\n"


def record_fast_trade_autopsy(
    summary: Mapping[str, Any],
    *,
    registry: ExperimentRegistry,
) -> str:
    """Persist aggregate runtime evidence as a non-authorizing Factory row."""
    payload_hash = hashlib.sha256(
        json.dumps(summary, default=str, sort_keys=True).encode("utf-8")
    ).hexdigest()
    experiment_id = f"fast_trade_autopsy_{payload_hash[:16]}"
    if registry.get(experiment_id) is not None:
        return experiment_id
    metrics = dict(summary.get("metrics") or {})
    metrics.update(
        {
            "median_hold_s": summary.get("median_hold_s"),
            "median_time_to_green_s": summary.get("median_time_to_green_s"),
            "seconds_in_red_observed_s": summary.get("seconds_in_red_observed_s"),
            "winner_giveback_rate": summary.get("winner_giveback_rate"),
            "loss_categories": summary.get("loss_categories") or {},
            "loss_category_metrics": summary.get("loss_category_metrics") or {},
            "next_experiments": summary.get("next_experiments") or [],
        }
    )
    hypothesis = {
        "hypothesis_id": experiment_id,
        "origin": "FAST_TRADE_AUTOPSY",
        "problem": "reduce avoidable fast-trade losses and winner giveback",
        "proposed_mechanism": "join broker-confirmed exits to point-in-time Firehose lifecycle traces",
        "features_required": "entry, quote, exit-trace, MFE, MAE, and broker-confirmed close evidence",
        "entry_rule": "observation only; no runtime authority",
        "exit_rule": "observation only; replay required before any challenger",
        "max_hold_s": 45,
    }
    try:
        return record_outcome(
            registry,
            hypothesis,
            payload_hash,
            "NO_EVIDENCE",
            "observation only; no replay or sealed-OOS challenger evidence",
            metrics,
        )
    except DuplicateExperimentError:
        return experiment_id


def outcome_learning_markdown(summary: Mapping[str, Any]) -> str:
    m = summary.get("metrics") or {}
    lines = [
        "# Outcome learning (reconciled exits)",
        "",
        "Label: `research_proxy`. Observed demo outcomes; not a profit guarantee.",
        "",
        f"- rows: {summary.get('n_rows')}",
        f"- exits: {summary.get('n_exits')}",
        "",
        "## Payoff geometry",
        "",
        f"- win_rate: {m.get('win_rate')}",
        f"- expectancy: {m.get('expectancy')}",
        f"- profit_factor: {m.get('profit_factor')}",
        f"- avg_win: {m.get('avg_win')}",
        f"- avg_loss: {m.get('avg_loss')}",
        f"- payoff_ratio: {m.get('payoff_ratio')}",
        f"- wins_erased_by_average_loss: {m.get('wins_erased_by_average_loss')}",
        f"- wins_erased_by_tail_loss: {m.get('wins_erased_by_tail_loss')}",
        f"- tail_loss: {m.get('tail_loss')}",
        f"- cosmetic_win_rate: {m.get('cosmetic_win_rate')}",
        "",
        "## By symbol",
        "",
    ]
    for row in (summary.get("by_symbol") or [])[:12]:
        lines.append(
            f"- {row['key']}: n={row['n']} exp={row['expectancy']} PF={row['profit_factor']} "
            f"erase_avg={row['wins_erased_by_average_loss']}"
        )
    lines += ["", "## By side", ""]
    for row in (summary.get("by_side") or []):
        lines.append(f"- {row['key']}: n={row['n']} exp={row['expectancy']} PF={row['profit_factor']}")
    lines += ["", "## By close reason", ""]
    for row in (summary.get("by_close_reason") or []):
        lines.append(
            f"- {row['key']}: n={row['n']} exp={row['expectancy']} PF={row['profit_factor']}"
        )
    return "\n".join(lines)
