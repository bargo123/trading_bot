#!/usr/bin/env python3
"""Where does measured edge actually exist, and what does $100/day require?

Two deterministic analyses over the real analogue index:

1. Per-state expectancy. The population can be negative while specific
   regime/structure/session/side states are positive. This finds them and applies
   the same 95% lower-bound test the runtime uses, so a state is only called an edge
   if the evidence supports it.

2. The $100/day gap. Derived from measured expectancy, not from a target. If
   expectancy is negative the required capital is reported as unavailable, because
   no amount of leverage fixes negative expectancy.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bot"))

from aegis.intel.expected_value import payoff_metrics  # noqa: E402
from aegis.intel.paths import INTEL_DIR  # noqa: E402

MIN_N = 20


def lower_bound_95(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return mean(values) - 1.96 * (pstdev(values) / math.sqrt(len(values)))


def analyse_states(rows: list[dict]) -> dict:
    groups: dict[tuple, list[float]] = defaultdict(list)
    keys = ("regime", "structure", "session", "side")
    for row in rows:
        try:
            outcome = float(row["outcome"])
        except (KeyError, TypeError, ValueError):
            continue
        groups[tuple(str(row.get(key)) for key in keys)].append(outcome)

    scored = []
    for state, outcomes in groups.items():
        if len(outcomes) < MIN_N:
            continue
        stats = payoff_metrics(outcomes)
        lower = lower_bound_95(outcomes)
        eligible = bool(
            stats["expectancy"] is not None
            and stats["expectancy"] > 0
            and lower is not None
            and lower > 0
            and not stats["cosmetic_win_rate"]
        )
        scored.append(
            {
                "state": dict(zip(keys, state)),
                "n": stats["n"],
                "n_losses": stats["n_losses"],
                "win_rate": stats["win_rate"],
                "expectancy_pips": stats["expectancy"],
                "profit_factor": stats["profit_factor"],
                "payoff_ratio": stats["payoff_ratio"],
                "avg_win": stats["avg_win"],
                "avg_loss": stats["avg_loss"],
                "tail_loss": stats["tail_loss"],
                "mean_lower_95": lower,
                "runtime_eligible": eligible,
            }
        )
    scored.sort(key=lambda row: (row["expectancy_pips"] or -999), reverse=True)
    return {
        "states_with_min_sample": len(scored),
        "runtime_eligible_states": sum(1 for row in scored if row["runtime_eligible"]),
        "positive_expectancy_states": sum(1 for row in scored if (row["expectancy_pips"] or 0) > 0),
        "best": scored[:12],
        "worst": scored[-8:],
        "all": scored,
    }


def gap_to_100_a_day(overall: dict, eligible_states: int) -> dict:
    """What would $100/day require, given measured expectancy?"""
    expectancy_pips = overall["expectancy"]
    # 0.01 lots on a 5-digit USD pair: 1 pip = $0.10.
    usd_per_pip_per_min_lot = 0.10
    per_trade_usd = None if expectancy_pips is None else expectancy_pips * usd_per_pip_per_min_lot
    report = {
        "measured_expectancy_pips_per_trade": expectancy_pips,
        "measured_profit_factor": overall["profit_factor"],
        "measured_win_rate": overall["win_rate"],
        "measured_payoff_ratio": overall["payoff_ratio"],
        "expectancy_usd_per_trade_at_0.01_lots": per_trade_usd,
        "runtime_eligible_states": eligible_states,
        "note": "",
    }
    if per_trade_usd is None or per_trade_usd <= 0:
        report["required_capital_for_100_per_day"] = "unavailable"
        report["note"] = (
            "Measured expectancy is not positive, so there is no capital level or lot "
            "size at which this strategy family yields $100/day. Leverage multiplies a "
            "negative number. The gap is an EDGE gap, not a capital gap."
        )
        return report
    trades_needed = 100.0 / per_trade_usd
    report["trades_per_day_needed_at_0.01_lots"] = trades_needed
    report["note"] = (
        "Positive measured expectancy. Trades/day needed is before slippage and "
        "assumes each qualified trade is independent, which correlated FX pairs are not."
    )
    return report


def main() -> int:
    index_path = INTEL_DIR / "analogue_index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    rows = payload.get("records") if isinstance(payload, dict) else payload
    rows = [row for row in rows if isinstance(row, dict)]
    provenance = str(payload.get("provenance") or payload.get("label") or "unknown")
    unit = str(payload.get("outcome_unit") or "unknown")

    overall = payoff_metrics([float(row["outcome"]) for row in rows if "outcome" in row])
    states = analyse_states(rows)
    gap = gap_to_100_a_day(overall, states["runtime_eligible_states"])

    out_dir = REPO / "bot" / "reports" / "claude"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "edge_and_gap.json").write_text(
        json.dumps(
            {
                "index": {"path": str(index_path), "provenance": provenance, "outcome_unit": unit, "n": len(rows)},
                "overall": overall,
                "states": states,
                "gap_to_100_per_day": gap,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    def _f(value, spec=".4f"):
        return "n/a" if value is None else format(value, spec) if isinstance(value, float) else str(value)

    lines = [
        "# Measured edge, and the gap to $100/day",
        "",
        f"Source: `{index_path.name}` — provenance **{provenance}**, outcomes in **{unit}**, "
        f"**{len(rows):,}** records.",
        "",
        "## Population-level result",
        "",
        "| metric | value |",
        "| --- | --- |",
        f"| trades | {overall['n']:,} |",
        f"| win rate | {_f(overall['win_rate'], '.2%')} |",
        f"| **expectancy** | **{_f(overall['expectancy'])} pips/trade** |",
        f"| **profit factor** | **{_f(overall['profit_factor'], '.3f')}** |",
        f"| avg win / avg loss | {_f(overall['avg_win'], '.2f')} / {_f(overall['avg_loss'], '.2f')} pips |",
        f"| payoff ratio | {_f(overall['payoff_ratio'], '.3f')} |",
        f"| breakeven WR required | {_f(overall['breakeven_wr'], '.2%')} |",
        f"| tail loss | {_f(overall['tail_loss'], '.1f')} pips |",
        f"| cosmetic win rate? | {overall['cosmetic_win_rate']} |",
        "",
        "This is the honest baseline for the M15 structural-thesis family, measured on",
        "real MT5 M1 history and **before spread costs**. It is not a positive-edge",
        "strategy at the population level.",
        "",
        "## Per-state breakdown",
        "",
        f"- States with at least {MIN_N} observations: **{states['states_with_min_sample']}**",
        f"- States with positive point expectancy: **{states['positive_expectancy_states']}**",
        f"- States that pass the runtime's 95% lower-bound test: **{states['runtime_eligible_states']}**",
        "",
        "### Best states by expectancy",
        "",
        "| regime | structure | session | side | n | WR | exp (pips) | PF | payoff | lower95 | runtime eligible |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in states["best"]:
        state = row["state"]
        lines.append(
            f"| {state['regime']} | {state['structure']} | {state['session']} | {state['side']} "
            f"| {row['n']} | {_f(row['win_rate'], '.1%')} | {_f(row['expectancy_pips'], '.2f')} "
            f"| {_f(row['profit_factor'], '.2f')} | {_f(row['payoff_ratio'], '.2f')} "
            f"| {_f(row['mean_lower_95'], '.2f')} | {row['runtime_eligible']} |"
        )

    lines += [
        "",
        "## Gap to $100/day",
        "",
        "| item | value |",
        "| --- | --- |",
    ]
    for key, value in gap.items():
        if key == "note":
            continue
        lines.append(f"| {key} | {_f(value) if isinstance(value, float) else value} |")
    lines += ["", f"**{gap['note']}**", ""]

    (out_dir / "edge_and_gap.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"overall": overall, "gap": gap,
                      "states_min_sample": states["states_with_min_sample"],
                      "positive_states": states["positive_expectancy_states"],
                      "eligible_states": states["runtime_eligible_states"]}, indent=2, default=str))
    print("\nTop 6 states:")
    for row in states["best"][:6]:
        print(f"  {row['state']} n={row['n']} exp={_f(row['expectancy_pips'], '.2f')} "
              f"pf={_f(row['profit_factor'], '.2f')} lower95={_f(row['mean_lower_95'], '.2f')} "
              f"eligible={row['runtime_eligible']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
