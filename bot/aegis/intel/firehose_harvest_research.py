"""Read-only evidence analysis for Firehose ticket lifecycles and replays."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping


USD_BUCKETS = (0.30, 0.50, 0.70, 0.80, 1.00)
_EXIT_EVENTS = frozenset({"pm_exit", "deal_exit", "deal_close", "firehose_close"})


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _field(record: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in record:
            return record[name]
    return None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower, upper = math.floor(index), math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _metric(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"status": "NO_COMPLETE_LIFECYCLE_EVIDENCE", "count": 0}
    return {
        "status": "OK",
        "count": len(values),
        "average": mean(values),
        "median": median(values),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
    }


def _empty_bucket() -> dict[str, Any]:
    return {
        "count": 0,
        "status": "NO_COMPLETE_LIFECYCLE_EVIDENCE",
        "realized_net_usd": None,
        "peak_unrealized_usd": None,
        "profit_capture_ratio": None,
        "post_threshold_hold_seconds": None,
        "cost_per_round_trip_usd": None,
    }


def _incomplete_journal_report() -> dict[str, Any]:
    unavailable = "INCOMPLETE_JOURNAL_EVIDENCE"
    buckets = {f"{value:.2f}_usd": {**_empty_bucket(), "status": unavailable} for value in USD_BUCKETS}
    erased = {
        f"{value:.2f}_usd": {"status": unavailable, "reached_count": 0, "count": 0, "rate": None}
        for value in USD_BUCKETS
    }
    metric = {"status": unavailable, "count": 0}
    return {
        "status": unavailable,
        "completed_tickets": 0,
        "incomplete_tickets": [],
        "buckets": buckets,
        "winner_distribution": dict(metric),
        "loser_distribution": dict(metric),
        "hold_time_seconds": dict(metric),
        "wins_erased_by_bucket": erased,
        "giveback_magnitude_usd": dict(metric),
        "time_between_close_and_entry_seconds": dict(metric),
        "round_trips_per_hour": None,
        "slot_utilization": None,
        "profit_capture_ratio": None,
        "cost_per_round_trip_usd": None,
        "max_loss_usd": None,
    }


def _confirmed_exit(event: Mapping[str, Any]) -> bool:
    return event.get("event") in _EXIT_EVENTS and event.get("confirmed") is True


def _complete_ticket(ticket: str, records: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    opens = [event for event in records if event.get("event") == "firehose_open"]
    traces = [event for event in records if event.get("event") == "firehose_exit_trace"]
    exits = [event for event in records if _confirmed_exit(event)]
    if len(opens) != 1 or not traces or len(exits) != 1:
        return None

    opened_at = _timestamp(_field(opens[0], "timestamp", "opened_at", "ts", "time"))
    closed_at = _timestamp(_field(exits[0], "timestamp", "closed_at", "ts", "time"))
    realized = _number(_field(exits[0], "realized_net_usd", "net_pnl_usd", "realized_pnl"))
    exit_cost = _number(_field(exits[0], "cost_usd", "total_cost_usd"))
    if opened_at is None or closed_at is None or closed_at < opened_at:
        return None
    if realized is None or exit_cost is None:
        return None
    side = opens[0].get("side")
    if side not in {"BUY", "SELL"}:
        return None

    observed: list[tuple[datetime, float, float]] = []
    for trace in traces:
        when = _timestamp(_field(trace, "timestamp", "ts", "time"))
        pnl = _number(_field(trace, "pnl_usd", "net_pnl_usd", "pnl"))
        mfe = _number(_field(trace, "mfe_usd", "mfe"))
        cost = _number(_field(trace, "cost_usd", "total_cost_usd"))
        liquidation_quote = _number(trace.get("liquidation_bid" if side == "BUY" else "liquidation_ask"))
        if when is None or pnl is None or mfe is None or cost is None or liquidation_quote is None or liquidation_quote <= 0:
            return None
        if when < opened_at or when > closed_at:
            return None
        observed.append((when, pnl, mfe))
    peak = max(item[2] for item in observed)
    if peak <= 0:
        return None
    return {
        "ticket": ticket,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "realized": realized,
        "cost": exit_cost,
        "peak": peak,
        "traces": observed,
        "slot_capacity": _number(_field(opens[0], "slot_capacity", "max_slots")),
    }


def analyze_ticket_lifecycles(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize only ticket records with observed open, traces, and confirmed exit."""
    events = list(events)
    if any(isinstance(event, Mapping) and event.get("event") == "journal_parse_error" for event in events):
        return _incomplete_journal_report()
    indexed: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        if not isinstance(event, Mapping):
            continue
        ticket = event.get("ticket")
        if isinstance(ticket, str) and ticket:
            indexed[ticket].append(event)

    complete: list[dict[str, Any]] = []
    incomplete: list[str] = []
    for ticket in sorted(indexed):
        lifecycle = _complete_ticket(ticket, indexed[ticket])
        if lifecycle is None:
            incomplete.append(ticket)
        else:
            complete.append(lifecycle)

    buckets = {f"{value:.2f}_usd": _empty_bucket() for value in USD_BUCKETS}
    for threshold in USD_BUCKETS:
        selected = []
        for lifecycle in complete:
            threshold_times = [when for when, pnl, _ in lifecycle["traces"] if pnl >= threshold]
            if threshold_times:
                selected.append((lifecycle, min(threshold_times)))
        if not selected:
            continue
        key = f"{threshold:.2f}_usd"
        realized = [item[0]["realized"] for item in selected]
        peaks = [item[0]["peak"] for item in selected]
        buckets[key] = {
            "status": "OK",
            "count": len(selected),
            "realized_net_usd": mean(realized),
            "peak_unrealized_usd": mean(peaks),
            "profit_capture_ratio": mean(item[0]["realized"] / item[0]["peak"] for item in selected),
            "post_threshold_hold_seconds": mean(
                (item[0]["closed_at"] - item[1]).total_seconds() for item in selected
            ),
            "cost_per_round_trip_usd": mean(item[0]["cost"] for item in selected),
        }

    realized = [item["realized"] for item in complete]
    winners = [value for value in realized if value > 0]
    losers = [value for value in realized if value < 0]
    holds = [(item["closed_at"] - item["opened_at"]).total_seconds() for item in complete]
    giveback_magnitudes = [item["peak"] - item["realized"] for item in complete if item["peak"] > 0]
    wins_erased_by_bucket = {}
    for threshold in USD_BUCKETS:
        reached = [item for item in complete if any(pnl >= threshold for _, pnl, _ in item["traces"])]
        erased = [item for item in reached if item["realized"] < threshold]
        wins_erased_by_bucket[f"{threshold:.2f}_usd"] = (
            {
                "status": "OK",
                "reached_count": len(reached),
                "count": len(erased),
                "rate": len(erased) / len(reached),
            }
            if reached
            else {"status": "NO_COMPLETE_LIFECYCLE_EVIDENCE", "reached_count": 0, "count": 0, "rate": None}
        )
    close_to_entry = []
    for later in sorted(complete, key=lambda item: item["opened_at"]):
        earlier_closes = [item["closed_at"] for item in complete if item["closed_at"] <= later["opened_at"]]
        if earlier_closes:
            close_to_entry.append((later["opened_at"] - max(earlier_closes)).total_seconds())
    span_seconds = (
        (max(item["closed_at"] for item in complete) - min(item["opened_at"] for item in complete)).total_seconds()
        if complete
        else 0.0
    )
    capacities = [item["slot_capacity"] for item in complete if item["slot_capacity"] and item["slot_capacity"] > 0]
    utilization = None
    if capacities and len(capacities) == len(complete) and span_seconds > 0:
        utilization = sum(holds) / (span_seconds * mean(capacities))

    status = "OK" if complete else "NO_COMPLETE_LIFECYCLE_EVIDENCE"
    return {
        "status": status,
        "completed_tickets": len(complete),
        "incomplete_tickets": incomplete,
        "buckets": buckets,
        "winner_distribution": _metric(winners),
        "loser_distribution": _metric(losers),
        "hold_time_seconds": _metric(holds),
        "wins_erased_by_bucket": wins_erased_by_bucket,
        "giveback_magnitude_usd": _metric(giveback_magnitudes),
        "time_between_close_and_entry_seconds": _metric(close_to_entry),
        "round_trips_per_hour": len(complete) / (span_seconds / 3600) if span_seconds > 0 else None,
        "slot_utilization": utilization,
        "profit_capture_ratio": mean(item["realized"] / item["peak"] for item in complete) if complete else None,
        "cost_per_round_trip_usd": mean(item["cost"] for item in complete) if complete else None,
        "max_loss_usd": min(losers) if losers else None,
    }


def compare_exit_policies(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Rank only fully observed, costed out-of-sample replay rows by expectancy."""
    policies: dict[str, list[float]] = defaultdict(list)
    rows_seen = 0
    for row in rows:
        if not isinstance(row, Mapping) or row.get("split") != "oos":
            continue
        rows_seen += 1
        policy = row.get("policy")
        gross = _number(row.get("gross_pnl_usd"))
        cost = _number(row.get("cost_usd"))
        if not isinstance(policy, str) or not policy or row.get("quote_observed") is not True or gross is None or cost is None:
            return {"status": "NO_EVIDENCE", "selection_metric": "oos_expectancy_after_cost", "winner": None}
        policies[policy].append(gross - cost)
    if not rows_seen or not policies:
        return {"status": "NO_EVIDENCE", "selection_metric": "oos_expectancy_after_cost", "winner": None}
    summary = {
        policy: {"count": len(values), "oos_expectancy_after_cost": mean(values)}
        for policy, values in policies.items()
    }
    winner = max(sorted(summary), key=lambda policy: summary[policy]["oos_expectancy_after_cost"])
    return {"status": "OK", "selection_metric": "oos_expectancy_after_cost", "winner": winner, "policies": summary}


def write_harvest_report(report: Mapping[str, Any], json_path: Path, markdown_path: Path) -> None:
    """Write only the explicitly requested JSON and Markdown evidence reports."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    unavailable = (
        "INCOMPLETE_JOURNAL_EVIDENCE"
        if report.get("status") == "INCOMPLETE_JOURNAL_EVIDENCE"
        else "NO_COMPLETE_LIFECYCLE_EVIDENCE"
    )

    def render(value: Any) -> str:
        return f"`{unavailable}`" if value is None else str(value)

    lines = [
        "# Firehose Harvest Evidence",
        "",
        f"Status: `{report.get('status', 'NO_EVIDENCE')}`",
        "",
        f"Completed tickets: {report.get('completed_tickets', 0)}",
        f"Incomplete tickets: {', '.join(report.get('incomplete_tickets', [])) or 'none'}",
        "",
        "## Buckets",
        "",
    ]
    for name, bucket in report.get("buckets", {}).items():
        lines.append(
            f"- {name}: `{bucket.get('status', 'NO_COMPLETE_LIFECYCLE_EVIDENCE')}`, "
            f"count={bucket.get('count', 0)}, realized_net_usd={render(bucket.get('realized_net_usd'))}, "
            f"peak_unrealized_usd={render(bucket.get('peak_unrealized_usd'))}, "
            f"profit_capture_ratio={render(bucket.get('profit_capture_ratio'))}, "
            f"post_threshold_hold_seconds={render(bucket.get('post_threshold_hold_seconds'))}, "
            f"cost_per_round_trip_usd={render(bucket.get('cost_per_round_trip_usd'))}"
        )
    lines.extend(["", "## Lifecycle Metrics", ""])
    for name in (
        "winner_distribution",
        "loser_distribution",
        "hold_time_seconds",
        "giveback_magnitude_usd",
        "time_between_close_and_entry_seconds",
    ):
        metric = report.get(name, {})
        lines.append(f"- {name}: `{metric.get('status', 'NO_COMPLETE_LIFECYCLE_EVIDENCE')}`, {metric}")
    for name in ("round_trips_per_hour", "slot_utilization", "profit_capture_ratio", "cost_per_round_trip_usd", "max_loss_usd"):
        lines.append(f"- {name}: {render(report.get(name))}")
    lines.extend(["", "## Threshold Erasure", ""])
    for name, metric in report.get("wins_erased_by_bucket", {}).items():
        lines.append(f"- wins_erased_by_bucket {name}: `{metric.get('status')}`, {metric}")
    policy = report.get("policy_comparison", {"status": "NO_EVIDENCE"})
    lines.extend(["", "## Policy Comparison", "", f"Policy comparison: `{policy.get('status', 'NO_EVIDENCE')}`"])
    if policy.get("status") == "OK":
        lines.append(f"selection_metric: {policy.get('selection_metric')}")
        lines.append(f"winner: {policy.get('winner')}")
        for name, evidence in policy.get("policies", {}).items():
            lines.append(
                f"- {name}: oos_count={evidence.get('count', '`NO_EVIDENCE`')}, "
                f"oos_expectancy_after_cost={evidence.get('oos_expectancy_after_cost', '`NO_EVIDENCE`')}, "
                f"profit_factor={evidence.get('profit_factor', '`NO_EVIDENCE`')}, "
                f"tail={evidence.get('tail', '`NO_EVIDENCE`')}, "
                f"drawdown={evidence.get('drawdown', '`NO_EVIDENCE`')}"
            )
    else:
        lines.append("selection_metric: `NO_EVIDENCE`")
        lines.append("winner: `NO_EVIDENCE`")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
