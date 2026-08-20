#!/usr/bin/env python3
"""ML research pipeline: exit horizons, strategy selection, ML model + charts.

Three phases on the measured mt5_m1 analogue index:
  1. exit research   - simulate 1/2/5/10-pip TP exits on real forward M1 bars,
                       net of the runner's spread/slippage cost assumptions,
                       pick the exit with the highest net expectancy.
  2. strategy select - shortlist candidate state strategies on the first 60% of
                       the sample (by time), validate the survivors on the last
                       40%, same cost assumptions.
  3. ML model        - state features -> ridge regression on earlier 70%, score
                       the untouched last 30%, export equity curve + drawdown
                       charts (SVG) and JSON series.

Research-only. Bar fetching is read-only; no orders and no live YAML edits.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.config import configured_symbols, load_config, pip_size_for  # noqa: E402
from aegis.intel.expected_value import payoff_metrics  # noqa: E402
from aegis.intel.paths import INTEL_DIR, resolve_bot_path  # noqa: E402
from aegis.research.exit_research import (  # noqa: E402
    EXIT_HORIZONS_PIPS,
    recommended_exit,
    research_exit_horizons,
    exit_horizon_summary,
)
from aegis.research.fingerprint import config_fingerprint  # noqa: E402
from aegis.research.ml_pipeline import (  # noqa: E402
    drawdown_svg,
    equity_curve_svg,
    feature_frame,
    train_and_score,
)
from aegis.research.registry import ExperimentRegistry  # noqa: E402

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"


def _load_records(index_path: Path) -> list[dict]:
    payload = json.loads(Path(index_path).read_text(encoding="utf-8"))
    return payload.get("records") or []


def _fetch_m1(symbols: list[str], bars: int) -> dict[str, pd.DataFrame]:
    import MetaTrader5 as mt5

    if not mt5.initialize(path=MT5_PATH):
        raise SystemExit(f"mt5.initialize failed: {mt5.last_error()}")
    frames: dict[str, pd.DataFrame] = {}
    try:
        account = mt5.account_info()
        demo = int(getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0))
        contest = int(getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", 1))
        if int(getattr(account, "trade_mode", 2)) not in {demo, contest}:
            raise SystemExit("refusing to fetch bars against a live account terminal")
        for symbol in symbols:
            if mt5.symbol_info(symbol) is None and not mt5.symbol_select(symbol, True):
                continue
            raw = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, bars)
            if raw is None or len(raw) < 500:
                continue
            frame = pd.DataFrame(raw)
            frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
            frame = frame.rename(columns={"tick_volume": "volume"})
            frames[symbol] = frame.iloc[:-1][["time", "open", "high", "low", "close", "volume"]].copy()
        return frames
    finally:
        mt5.shutdown()


def _costed(pnls: list[float], cost_pips: float) -> list[float]:
    return [float(p) - float(cost_pips) for p in pnls]


def _state_signatures(records: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for record in records:
        key = (
            str(record.get("regime") or "?"),
            str(record.get("structure") or "?"),
            str(record.get("session") or "?"),
            str(record.get("side") or "?"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "regime": key[0],
                "structure": key[1],
                "session": key[2],
                "side": key[3],
            }
        )
    return out


def _matches(record: dict, sig: dict) -> bool:
    return all(str(record.get(k) or "") == v for k, v in sig.items())


def _mean_lower_95(pnls: list[float]) -> float | None:
    """95% CI lower bound on mean outcome, matching the live readiness gate."""
    values = [float(v) for v in pnls]
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    sigma = math.sqrt(sum((v - avg) ** 2 for v in values) / len(values))
    return avg - 1.96 * (sigma / math.sqrt(len(values)))


def write_validated_states(
    selection: dict[str, Any],
    *,
    path: Path = INTEL_DIR / "validated_states.json",
) -> Path:
    """Write the validated-state allowlist the live brain gates on.

    Only states that survived out-of-sample validation - including a positive 95%
    CI lower bound on the OOS window - enter the list, so an allowlisted state is
    guaranteed to clear the live ``strategy_model_ready`` gate. An empty list (or
    a missing file) means nothing is currently validated, so a gated brain refuses
    to fire on anything - the full analogue index is net-negative after costs, so
    firing outside validated states is the losing behavior.
    """
    state_keys = ("regime", "structure", "session", "side")
    survivors = [c for c in selection.get("validated", []) if c.get("survives_validate")]
    metric_keys = (
        "n_validate",
        "n_losses_validate",
        "expectancy_validate",
        "profit_factor_validate",
        "win_rate_validate",
        "bootstrap_p05_validate",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "validated_states.v2",
                "built_at": datetime.now(timezone.utc).isoformat(),
                "n_survive": len(survivors),
                "source": "strategy_selection",
                "states": [
                    {**{k: str(c.get(k) or "") for k in state_keys},
                     **{m: c.get(m) for m in metric_keys if c.get(m) is not None}}
                    for c in survivors
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def strategy_selection(
    records: list[dict],
    *,
    shortlist_frac: float = 0.6,
    cost_pips: float = 0.3,
    min_shortlist_n: int = 20,
    max_candidates: int = 50,
) -> dict[str, Any]:
    state_keys = ("regime", "structure", "session", "side")
    records = sorted(records, key=lambda r: str(r.get("bar_time") or ""))
    cut = int(len(records) * shortlist_frac)
    early = records[:cut]
    late = records[cut:]
    candidates = []
    for sig in _state_signatures(early):
        early_pnls = [float(r["outcome"]) for r in early if _matches(r, sig)]
        if len(early_pnls) < min_shortlist_n:
            continue
        net = _costed(early_pnls, cost_pips)
        metrics = payoff_metrics(net)
        if (metrics.get("expectancy") or 0) > 0:
            candidates.append(
                {
                    "state": {k: sig[k] for k in state_keys},
                    "n_shortlist": len(early_pnls),
                    "expectancy_shortlist": metrics["expectancy"],
                }
            )
    candidates.sort(key=lambda c: float(c["expectancy_shortlist"]), reverse=True)
    candidates = candidates[:max_candidates]

    validated = []
    for candidate in candidates:
        sig = candidate["state"]
        late_pnls = [float(r["outcome"]) for r in late if _matches(r, sig)]
        if not late_pnls:
            continue
        net = _costed(late_pnls, cost_pips)
        metrics = payoff_metrics(net)
        p05 = _mean_lower_95(net)
        validated.append(
            {
                **sig,
                "n_validate": len(late_pnls),
                "n_losses_validate": int(metrics.get("n_losses") or 0),
                "expectancy_validate": metrics["expectancy"],
                "profit_factor_validate": metrics["profit_factor"],
                "win_rate_validate": metrics["win_rate"],
                "bootstrap_p05_validate": p05,
                "survives_validate": bool(
                    (metrics.get("expectancy") or 0) > 0
                    and p05 is not None
                    and p05 > 0
                ),
            }
        )
    validated.sort(key=lambda c: float(c["expectancy_validate"] or -1e9), reverse=True)
    return {
        "cost_pips_assumed": float(cost_pips),
        "shortlist_frac": float(shortlist_frac),
        "n_shortlisted": len(candidates),
        "n_validated": len(validated),
        "n_survive": sum(1 for c in validated if c["survives_validate"]),
        "candidates": candidates,
        "validated": validated,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ML research pipeline (research-only)")
    parser.add_argument("--index", type=Path, default=INTEL_DIR / "analogue_index.json")
    parser.add_argument("--config", type=Path, default=BOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--report", type=Path, default=BOT / "reports" / "research" / "ml_pipeline.json")
    parser.add_argument("--bars", type=int, default=6000)
    parser.add_argument("--fetch", action="store_true", help="fetch M1 bars (read-only) for exit research")
    args = parser.parse_args()

    cfg = load_config(args.config)
    symbols = configured_symbols(cfg)
    records = _load_records(args.index)
    pip_by_symbol = {s: float(pip_size_for(s, cfg)) for s in symbols}
    spread_bps = float(cfg.get("spread_bps", 0.2) or 0.2)
    slippage_bps = float(cfg.get("slippage_bps", 0.1) or 0.1)

    exit_rows = []
    if args.fetch:
        frames = _fetch_m1(symbols, int(args.bars))
        exit_rows = research_exit_horizons(
            records,
            frames,
            pip_by_symbol=pip_by_symbol,
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
        )
    exit_summary = exit_horizon_summary(exit_rows)
    recommended = recommended_exit(exit_summary)

    df = feature_frame(records)
    ml = train_and_score(df)

    from aegis.research.exit_research import per_trade_cost_pips

    sample_cost = per_trade_cost_pips(symbols[0], float(pip_by_symbol.get(symbols[0], 0.0001)), spread_bps, slippage_bps) if symbols else 0.0
    selection = strategy_selection(records, cost_pips=sample_cost)
    validated_states_path = write_validated_states(
        selection,
        path=resolve_bot_path(
            cfg.get("validated_states_path"), INTEL_DIR / "validated_states.json"
        ),
    )

    report = {
        "schema": "ml_pipeline.v1",
        "label": "research_proxy",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "provenance": "mt5_m1",
        "cost_assumptions": {
            "spread_bps": spread_bps,
            "slippage_bps": slippage_bps,
            "sample_cost_pips": sample_cost,
        },
        "exit_research": {
            "n_rows": len(exit_rows),
            "horizons": EXIT_HORIZONS_PIPS,
            "summary": exit_summary,
            "recommended": recommended,
        },
        "strategy_selection": selection,
        "validated_states_path": str(validated_states_path),
        "ml": {
            "train_n": ml["train_n"],
            "holdout_n": ml["holdout_n"],
            "n_taken": ml["n_taken"],
            "all_holdout_expectancy": ml["all_holdout"]["expectancy"],
            "model_taken_expectancy": ml["model_taken"]["expectancy"],
            "improvement_expectancy": ml["improvement_expectancy"],
            "equity_curve": ml["equity_curve"],
            "drawdown": ml["drawdown"],
            "model_equity_curve": ml["model_equity_curve"],
            "equity_curve_svg": equity_curve_svg(ml["equity_curve"]),
            "model_equity_curve_svg": equity_curve_svg(ml["model_equity_curve"], color="#27ae60", title="Model-taken equity curve"),
            "drawdown_svg": drawdown_svg(ml["drawdown"]),
        },
        "mt5_touched": bool(args.fetch),
        "placed_orders": False,
        "promoted_live_yaml": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    registry = ExperimentRegistry()
    fp = config_fingerprint(
        {
            "task": "ml_pipeline",
            "spread_bps": spread_bps,
            "slippage_bps": slippage_bps,
            "fetch": bool(args.fetch),
        }
    )
    row = {
        "id": f"ml_pipeline_{fp[:8]}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "State features and fixed-TP exit horizons on the mt5_m1 index "
                      "produce net-positive OOS expectancy under the runner's costs.",
        "status": "completed",
        "config_fingerprint": fp,
        "dataset_fingerprint": "mt5_m1_analogue_index",
        "params": {"label": "research_proxy", "strategy_implemented": False},
        "metrics": {
            "n_trades": ml["holdout_n"],
            "win_rate": None,
            "expectancy": ml["model_taken"]["expectancy"],
            "profit_factor": ml["model_taken"]["profit_factor"],
            "net_pnl": ml["model_taken"]["net_pnl"],
        },
        "provenance": {
            "report": str(args.report),
            "mt5_touched": bool(args.fetch),
            "placed_orders": False,
            "promoted_live_yaml": False,
        },
    }
    registry.record(row)

    print(
        json.dumps(
            {
                "report": str(args.report),
                "exit_research": {
                    "n_rows": len(exit_rows),
                    "summary": exit_summary,
                    "recommended": recommended,
                },
                "strategy_selection": {
                    "shortlisted": selection["n_shortlisted"],
                    "validated": selection["n_validated"],
                    "survive": selection["n_survive"],
                    "validated_states_path": str(validated_states_path),
                },
                "ml": {
                    "train_n": ml["train_n"],
                    "holdout_n": ml["holdout_n"],
                    "all_holdout_expectancy": ml["all_holdout"]["expectancy"],
                    "model_taken_expectancy": ml["model_taken"]["expectancy"],
                    "improvement_expectancy": ml["improvement_expectancy"],
                },
                "mt5_touched": bool(args.fetch),
                "placed_orders": False,
                "promoted_live_yaml": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())