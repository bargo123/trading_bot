#!/usr/bin/env python3
"""Tune HALE on development/validation, then open each frozen holdout once."""
from __future__ import annotations

import argparse
import itertools
import math
import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aegis.basket_backtest import run_basket_backtest
from aegis.hale import prepare_hale, sig_hale_fade, sig_hale_pullback
from tune_cafb_basket import fmt_pf, get_data, metric_line, metrics, split_frames

REPORT = ROOT / "reports" / "HALE_BASKET.md"
SEARCH = ROOT / "reports" / "hale_search_results.csv"
TUNED = ROOT / "config_hale_basket.tuned.yaml"

SignalFn = Callable[[pd.Series, dict[str, Any]], Any]


def stable_score(
    dev: dict[str, Any],
    val: dict[str, Any],
    min_dev: int,
    min_val: int,
) -> float:
    """Prefer repeatable net expectancy; high raw win rate is only a tiebreaker."""
    if dev["trades"] < min_dev or val["trades"] < min_val:
        return -1e9
    dev_pf = float(dev["profit_factor"])
    val_pf = float(val["profit_factor"])
    dev_pf_cap = 5.0 if not math.isfinite(dev_pf) else min(dev_pf, 5.0)
    val_pf_cap = 5.0 if not math.isfinite(val_pf) else min(val_pf, 5.0)
    stable = (
        dev["expectancy_r"] > 0
        and val["expectancy_r"] > 0
        and dev_pf > 1
        and val_pf > 1
    )
    return (
        (100.0 if stable else -100.0)
        + 100.0 * min(dev["expectancy_r"], val["expectancy_r"])
        + 5.0 * min(dev_pf_cap, val_pf_cap)
        + 0.05 * min(dev["win_rate"], val["win_rate"])
        + 0.15 * min(dev["trades_per_day"], val["trades_per_day"], 100.0)
        - 0.25 * max(dev["max_drawdown_pct"], val["max_drawdown_pct"])
    )


def base_config(path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(path.read_text())
    return {
        **cfg,
        "starting_equity": 100.0,
        "risk_percent": 2.0,
        "high_risk_mode": "traditional",
        "high_risk_safe": True,
        "allow_unsafe_high_risk": False,
        "hr_risk_max_cap": 20.0,
        "hr_max_consecutive_losses": 999,
        "hr_equity_floor_frac": 0.10,
        "max_positions": 2,
        "max_portfolio_heat_percent": 4.0,
        "max_currency_exposure": 2,
        "max_gross_leverage": 30.0,
        "min_units": 1000.0,
        "unit_step": 1000.0,
        "spread_bps": 0.6,
        "slippage_bps": 0.3,
        "commission_bps": 0.0,
        "commission_round_trip_usd": 0.0,
        "cost_buffer": 1.5,
        "negative_balance_protection": True,
    }


def _run_metrics(
    name: str,
    segment: str,
    frames: dict[str, pd.DataFrame],
    cfg: dict[str, Any],
    signal_fn: SignalFn,
) -> dict[str, Any]:
    result = run_basket_backtest(
        frames,
        cfg,
        prepare_fn=lambda frame, _cfg: frame,
        signal_fn=signal_fn,
    )
    return metrics(name, segment, frames, result, cfg)


def _selection_record(
    family: str,
    timeframe: str,
    cfg: dict[str, Any],
    score: float,
    dev_m: dict[str, Any],
    val_m: dict[str, Any],
) -> dict[str, Any]:
    parameters = {
        key: value
        for key, value in cfg.items()
        if key.startswith("hale_") or key in {"cafb_htf_adx_min", "max_hold_bars"}
    }
    return {
        "family": family,
        "timeframe": timeframe,
        **parameters,
        "score": score,
        **{f"dev_{key}": value for key, value in dev_m.items() if key not in {"strategy", "segment"}},
        **{f"val_{key}": value for key, value in val_m.items() if key not in {"strategy", "segment"}},
    }


def tune_family(
    raw: dict[str, pd.DataFrame],
    cfg: dict[str, Any],
    timeframe: str,
    family: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if family == "fade":
        signal_fn = sig_hale_fade
        feature_grid = itertools.product([3, 4], [15, 25])
        parameter_grid = list(
            itertools.product(
                [0.75, 1.5],
                [0.5, 0.8],
                [0.2, 0.5],
                [0.10, 0.25],
                [0.5, 0.8, 1.2],
            )
        )
    elif family == "pullback":
        signal_fn = sig_hale_pullback
        feature_grid = itertools.product([1, 2, 3], [15, 25])
        parameter_grid = list(itertools.product([0.5, 1.0], [0.10, 0.25], [0.5, 0.8, 1.2]))
    else:
        raise ValueError(f"Unknown HALE family: {family}")

    min_dev = 20 if timeframe == "1m" else 40
    min_val = 8 if timeframe == "1m" else 15
    context_minutes = 5 if timeframe == "1m" else 15
    rows: list[dict[str, Any]] = []
    best: tuple[float, dict[str, Any], dict[str, pd.DataFrame], dict[str, Any], dict[str, Any]] | None = None

    for feature_value, adx_min in feature_grid:
        feature_cfg = {
            **cfg,
            "signal_mode": f"hale_{family}",
            "algo": f"hale_{family}",
            "cafb_context_minutes": context_minutes,
            "cafb_htf_adx_min": adx_min,
        }
        if family == "fade":
            feature_cfg["hale_impulse_bars"] = feature_value
        else:
            feature_cfg["hale_pullback_bars"] = feature_value
        prepared = {symbol: prepare_hale(frame, feature_cfg) for symbol, frame in raw.items()}
        dev = split_frames(prepared, "development")
        val = split_frames(prepared, "validation")

        for parameters in parameter_grid:
            candidate = dict(feature_cfg)
            if family == "fade":
                (
                    candidate["hale_impulse_atr"],
                    candidate["hale_contraction_ratio"],
                    candidate["hale_level_atr"],
                    candidate["hale_stop_buffer_atr"],
                    candidate["hale_target_r"],
                ) = parameters
            else:
                (
                    candidate["hale_pullback_near_atr"],
                    candidate["hale_stop_buffer_atr"],
                    candidate["hale_target_r"],
                ) = parameters
            dev_m = _run_metrics(f"hale_{family}", "development", dev, candidate, signal_fn)
            val_m = _run_metrics(f"hale_{family}", "validation", val, candidate, signal_fn)
            score = stable_score(dev_m, val_m, min_dev, min_val)
            rows.append(_selection_record(family, timeframe, candidate, score, dev_m, val_m))
            if best is None or score > best[0]:
                best = (score, candidate, prepared, dev_m, val_m)

    assert best is not None
    score, selected_cfg, prepared, dev_m, val_m = best
    selection_qualified = (
        dev_m["trades"] >= min_dev
        and val_m["trades"] >= min_val
        and dev_m["expectancy_r"] > 0
        and val_m["expectancy_r"] > 0
        and dev_m["profit_factor"] > 1
        and val_m["profit_factor"] > 1
    )
    hold = split_frames(prepared, "holdout")
    hold_m = _run_metrics(f"hale_{family}", "holdout", hold, selected_cfg, signal_fn)
    selected = {
        **selected_cfg,
        "_family": family,
        "_timeframe": timeframe,
        "_selection_score": score,
        "_selection_qualified": selection_qualified,
        "_development": dev_m,
        "_validation": val_m,
        "_holdout": hold_m,
    }
    print(
        f"HALE {family:8} {timeframe:>2} HOLDOUT n={hold_m['trades']:4d} "
        f"WR={hold_m['win_rate']:6.2f}% E[R]={hold_m['expectancy_r']:+.3f} "
        f"PF={fmt_pf(hold_m['profit_factor'])} DD={hold_m['max_drawdown_pct']:.2f}% "
        f"eq={hold_m['end_equity']:.2f}",
        flush=True,
    )
    return selected, rows


def _selected_signal(selected: dict[str, Any]) -> SignalFn:
    return sig_hale_fade if selected["_family"] == "fade" else sig_hale_pullback


def stress_selected(
    raw: dict[str, pd.DataFrame],
    selected: dict[str, Any],
) -> list[dict[str, Any]]:
    cfg = {key: value for key, value in selected.items() if not key.startswith("_")}
    signal_fn = _selected_signal(selected)
    prepared = {symbol: prepare_hale(frame, cfg) for symbol, frame in raw.items()}
    hold = split_frames(prepared, "holdout")
    family = selected["_family"]
    timeframe = selected["_timeframe"]
    rows: list[dict[str, Any]] = []

    for scale in [1.0, 1.5, 2.0]:
        candidate = {
            **cfg,
            "spread_bps": 0.4 * scale,
            "slippage_bps": 0.2 * scale,
            "commission_round_trip_usd": 0.0,
            "cost_buffer": scale,
            "risk_percent": 2.0,
        }
        row = _run_metrics(f"hale_{family}", f"holdout_cost_{scale:.1f}x", hold, candidate, signal_fn)
        row.update({"family": family, "timeframe": timeframe, "cost_scale": scale, "risk_percent": 2.0})
        rows.append(row)

    for risk_pct in [1.0, 2.0, 5.0, 10.0, 20.0]:
        candidate = {
            **cfg,
            "spread_bps": 0.6,
            "slippage_bps": 0.3,
            "commission_round_trip_usd": 0.0,
            "cost_buffer": 1.5,
            "risk_percent": risk_pct,
            "hr_risk_max_cap": risk_pct,
            "max_portfolio_heat_percent": 2.0 * risk_pct,
            "max_daily_loss_percent": max(8.0, 2.0 * risk_pct),
            "max_total_drawdown_percent": max(30.0, 2.0 * risk_pct),
        }
        row = _run_metrics(f"hale_{family}", f"holdout_risk_{risk_pct:.0f}", hold, candidate, signal_fn)
        row.update({"family": family, "timeframe": timeframe, "cost_scale": 1.5, "risk_percent": risk_pct})
        rows.append(row)

    for label, cost_buffer in [("holdout_ib_4usd_gate", 1.5), ("holdout_ib_4usd_forced", 0.0)]:
        candidate = {
            **cfg,
            "spread_bps": 0.6,
            "slippage_bps": 0.3,
            "commission_round_trip_usd": 4.0,
            "cost_buffer": cost_buffer,
            "risk_percent": 2.0,
        }
        row = _run_metrics(f"hale_{family}", label, hold, candidate, signal_fn)
        row.update({"family": family, "timeframe": timeframe, "cost_scale": 1.5, "risk_percent": 2.0})
        rows.append(row)
    return rows


def _positive_pnl_concentration(selected: dict[str, Any], raw: dict[str, pd.DataFrame]) -> float:
    cfg = {key: value for key, value in selected.items() if not key.startswith("_")}
    prepared = {symbol: prepare_hale(frame, cfg) for symbol, frame in raw.items()}
    hold = split_frames(prepared, "holdout")
    result = run_basket_backtest(
        hold,
        cfg,
        prepare_fn=lambda frame, _cfg: frame,
        signal_fn=_selected_signal(selected),
    )
    if result.total_trades == 0:
        return float("inf")
    winners = result.trades[result.trades["pnl"] > 0]
    total = float(winners["pnl"].sum())
    if total <= 0:
        return float("inf")
    by_symbol = winners.groupby("symbol")["pnl"].sum()
    return float(by_symbol.max() / total)


def promotion_gates(
    selected: dict[str, Any],
    raw: dict[str, pd.DataFrame],
    stresses: list[dict[str, Any]],
) -> dict[str, Any]:
    hold = selected["_holdout"]
    concentration = _positive_pnl_concentration(selected, raw)
    two_x = next(row for row in stresses if row["segment"] == "holdout_cost_2.0x")
    gates = {
        "holdout_trades_at_least_100": hold["trades"] >= 100,
        "holdout_expectancy_positive": hold["expectancy_r"] > 0,
        "holdout_pf_above_1": hold["profit_factor"] > 1,
        "holdout_survived": hold["end_equity"] > 0 and hold["halt_reason"] == "none",
        "positive_pnl_concentration_at_most_60pct": concentration <= 0.60,
        "two_x_cost_survived_with_edge": two_x["end_equity"] > 0 and two_x["expectancy_r"] > 0 and two_x["profit_factor"] > 1,
    }
    return {**gates, "max_positive_pnl_concentration": concentration, "promoted": all(gates.values())}


def write_report(
    symbols: list[str],
    data_m5: dict[str, pd.DataFrame],
    data_m1: dict[str, pd.DataFrame],
    selections: list[dict[str, Any]],
    primary: dict[str, Any],
    stresses: list[dict[str, Any]],
    gates: dict[str, Any],
) -> None:
    hold = primary["_holdout"]
    observed_perfect = hold["trades"] > 0 and hold["win_rate"] >= 99.999
    verdict = (
        "PROMOTED to a future MT5 tick-paper candidate; it is not enabled in IB paper."
        if gates["promoted"]
        else "REJECTED for paper promotion; the existing paper bot remains stopped."
    )
    if observed_perfect:
        wr_note = "The primary holdout happened to be 100% WR, but this is a finite observation, not an always-win edge."
    else:
        wr_note = "No primary frozen holdout achieved 100% WR after costs."
    qualified_count = sum(bool(selected["_selection_qualified"]) for selected in selections)
    lines = [
        "# HALE Basket — measured coarse-screen results",
        "",
        f"Symbols: `{', '.join(symbols)}` · one shared starting equity: **$100**",
        "",
        f"**Verdict: {verdict} {wr_note}**",
        "",
        "HALE tests the added Heikin-Ashi book's strongest auditable rule: a contracted same-color impulse at an objective level, followed by the first opposite completed HA bar. HA prices generate signals only; all entries use the next real OHLC open.",
        f"The search evaluated 528 development/validation configurations. **{qualified_count} of 4 family/timeframe selections passed the minimum-sample plus positive development/validation E[R] and PF gates.** The primary below is therefore diagnostic, not qualified.",
        "",
        "## Development, validation, and frozen holdout selections",
        "",
    ]
    for selected in selections:
        lines.extend(
            [
                f"### {selected['_family'].title()} · {'M5' if selected['_timeframe'] == '5m' else 'M1'}",
                "",
                f"- Development: {metric_line(selected['_development'])}",
                f"- Validation: {metric_line(selected['_validation'])}",
                f"- Frozen holdout: {metric_line(selected['_holdout'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## Primary selected configuration",
            "",
            f"Family: **{primary['_family']}** · timeframe: **{primary['_timeframe']}** · selected without holdout metrics.",
            f"Development/validation selection gate: **{'PASS' if primary['_selection_qualified'] else 'FAIL'}**.",
            "",
            "```yaml",
            yaml.safe_dump(
                {
                    key: value
                    for key, value in primary.items()
                    if key.startswith("hale_") or key in {"cafb_htf_adx_min", "max_hold_bars"}
                },
                sort_keys=False,
            ).strip(),
            "```",
            "",
            "## Mandatory primary holdout numbers",
            "",
            f"- Sample: `{hold['start_utc']}` to `{hold['end_utc']}` ({hold['span_days']:.2f} calendar days).",
            f"- Closed trades: **{hold['trades']}**; trades/day: **{hold['trades_per_day']:.2f}**.",
            f"- WR: **{hold['win_rate']:.2f}%** (Wilson 95% CI **{hold['win_ci_low']:.2f}–{hold['win_ci_high']:.2f}%**).",
            f"- Net E[R]: **{hold['expectancy_r']:+.4f}**; PF: **{fmt_pf(hold['profit_factor'])}**.",
            f"- Max DD: **{hold['max_drawdown_pct']:.2f}%**; equity: **$100.00 → ${hold['end_equity']:.2f}**.",
            f"- Net P&L/day: **${hold['profit_per_day']:+.2f}** per historical calendar day; halt: **{hold['halt_reason']}**; ambiguous exits: **{hold['ambiguous_exits']}**.",
            "- Primary costs: 0.6 bps spread + 0.3 bps slippage per side, no fixed commission; stop/target collisions are stop-first.",
            "",
            "## Cost and aggressive-sizing stress",
            "",
            "| Test | Trades | Trades/day | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in stresses:
        lines.append(
            f"| {row['segment']} | {row['trades']} | {row['trades_per_day']:.2f} | {row['win_rate']:.1f}% | "
            f"{row['expectancy_r']:+.3f} | {fmt_pf(row['profit_factor'])} | {row['max_drawdown_pct']:.1f}% | "
            f"${row['end_equity']:.2f} | ${row['profit_per_day']:+.2f} | {row['halt_reason']} |"
        )
    lines.extend(["", "## Promotion gates", ""])
    for key, value in gates.items():
        if key == "max_positive_pnl_concentration":
            rendered = "undefined" if not math.isfinite(float(value)) else f"{100.0 * float(value):.1f}%"
        else:
            rendered = "PASS" if bool(value) else "FAIL"
        lines.append(f"- `{key}`: **{rendered}**")
    lines.extend(["", "## Data windows", ""])
    for timeframe, data in [("5m", data_m5), ("1m", data_m1)]:
        for symbol, frame in data.items():
            lines.append(
                f"- {timeframe} `{symbol}`: {len(frame)} bars, `{frame.time.iloc[0]}` to `{frame.time.iloc[-1]}`, "
                f"actual interval `{frame.attrs.get('actual_interval', timeframe)}`."
            )
    lines.extend(
        [
            "",
            "## Limits and decision",
            "",
            "- Yahoo OHLC cannot validate tick ordering, live spread at the level, or sub-minute bid/ask fills. This is a conservative coarse screen, not an MT5 scalp proof.",
            "- The IB-like `$4` rows expose the fixed fee that earlier bps-only basket tests omitted. The `gate` row declines uneconomic trades; the `forced` row shows the result if that guard is bypassed.",
            "- Aggressive risk changes the equity path but not the underlying E[R]. No sizing row authorizes live trading.",
            "- Profit/day is historical P&L divided by calendar span, not a promised daily income.",
            f"- Full development/validation grid: `{SEARCH}`.",
            "",
        ]
    )
    REPORT.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config_hale_basket.yaml")
    args = parser.parse_args()
    cfg = base_config(args.config)
    symbols = list(cfg["symbols"])
    data_m5 = get_data(symbols, "5m", 59, False)
    data_m1 = get_data(symbols, "1m", 7, False)

    selections: list[dict[str, Any]] = []
    search_rows: list[dict[str, Any]] = []
    for timeframe, raw in [("5m", data_m5), ("1m", data_m1)]:
        for family in ["fade", "pullback"]:
            selected, rows = tune_family(raw, cfg, timeframe, family)
            selections.append(selected)
            search_rows.extend(rows)
    pd.DataFrame(search_rows).to_csv(SEARCH, index=False)

    primary = max(selections, key=lambda selected: float(selected["_selection_score"]))
    primary_data = data_m1 if primary["_timeframe"] == "1m" else data_m5
    stresses = stress_selected(primary_data, primary)
    gates = promotion_gates(primary, primary_data, stresses)

    tuned = {key: value for key, value in primary.items() if not key.startswith("_")}
    tuned.update(
        {
            "timeframe": primary["_timeframe"],
            "lookback_days": 7 if primary["_timeframe"] == "1m" else 59,
            "signal_mode": f"hale_{primary['_family']}",
            "algo": f"hale_{primary['_family']}",
            "mode": "research",
            "paper_promoted": bool(gates["promoted"]),
            "test_name": "hale_basket_tuned_coarse_screen",
        }
    )
    TUNED.write_text(yaml.safe_dump(tuned, sort_keys=False))
    write_report(symbols, data_m5, data_m1, selections, primary, stresses, gates)
    print(f"PRIMARY {primary['_family']} {primary['_timeframe']} promoted={gates['promoted']}")
    print(f"REPORT {REPORT}")
    print(f"CONFIG {TUNED}")


if __name__ == "__main__":
    main()
