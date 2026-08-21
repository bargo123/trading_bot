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
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.config import configured_symbols, load_config, pip_size_for  # noqa: E402
from aegis.intel.expected_value import payoff_metrics  # noqa: E402
from aegis.intel.paths import INTEL_DIR, resolve_bot_path  # noqa: E402
from aegis.research.exit_research import (  # noqa: E402
    EXIT_HORIZONS_PIPS,
    bps_to_pips,
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


def symbol_cost_pips(
    pip_by_symbol: dict[str, float],
    *,
    spread_bps: float,
    slippage_bps: float,
    commission_round_trip_usd: float = 0.0,
) -> dict[str, dict[str, float]]:
    """Per-symbol round-trip cost model (P4).

    One universal cost across 26 instruments is wrong: JPY pairs and crosses
    have very different pip sizes and spreads. Cost per symbol = spread +
    slippage converted to that symbol's pips, plus commission expressed in
    pips via the 0.01-lot pip value. Returns
    {symbol: {cost_pips, spread_pips, slippage_pips, commission_pips}}.
    """
    out: dict[str, dict[str, float]] = {}
    for symbol, pip in pip_by_symbol.items():
        if not pip or pip <= 0:
            continue
        spread_pips = bps_to_pips(spread_bps, symbol, pip)
        slippage_pips = bps_to_pips(slippage_bps, symbol, pip)
        # $X round-trip on a 0.01-lot clip: pips of cost = X / pip-value(0.01 lot).
        pip_value_per_001_lot = float(pip) * 1000.0  # ~USD per pip for 0.01 lot FX
        commission_pips = (
            float(commission_round_trip_usd) / max(pip_value_per_001_lot, 1e-9)
            if commission_round_trip_usd
            else 0.0
        )
        out[symbol.upper()] = {
            "cost_pips": round(spread_pips + slippage_pips + max(commission_pips, 0.0), 4),
            "spread_pips": round(spread_pips, 4),
            "slippage_pips": round(slippage_pips, 4),
            "commission_pips": round(max(commission_pips, 0.0), 4),
        }
    return out


def _max_drawdown_pips(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    dd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        dd = min(dd, equity - peak)
    return round(dd, 4)


# Out-of-sample qualification gates (defect 8): consistent with runtime/champion
# safety. expectancy>0 AND p05>0 alone are NOT enough - sample size, loss tail,
# profit factor and payoff symmetry must all hold.
MIN_OOS_N = 10
MIN_OOS_LOSSES = 5
MIN_OOS_PAYOFF = 0.25  # avg_loss may not erase more than 4x avg_win


def oos_gate(vm: dict[str, Any]) -> tuple[bool, str]:
    """Deterministic OOS qualification gate for one candidate metrics dict."""
    if int(vm.get("n") or 0) < MIN_OOS_N:
        return False, f"insufficient_oos_n:{vm.get('n')}"
    if int(vm.get("n_losses") or 0) < MIN_OOS_LOSSES:
        return False, f"insufficient_loss_tail:{vm.get('n_losses')}"
    if float(vm.get("expectancy") or 0.0) <= 0:
        return False, "expectancy_not_positive"
    pf = vm.get("profit_factor")
    if pf is None or float(pf) <= 1.0:
        return False, "profit_factor_not_above_one"
    p05 = vm.get("bootstrap_p05")
    if p05 is None or float(p05) <= 0:
        return False, "bootstrap_p05_not_positive"
    payoff = vm.get("payoff")
    if payoff is not None and float(payoff) < MIN_OOS_PAYOFF:
        return False, f"payoff_below_floor:{payoff}"
    return True, "ok"


def _state_metrics(pnls: list[float]) -> dict[str, Any]:
    metrics = payoff_metrics(pnls)
    avg_win = metrics.get("avg_win")
    avg_loss = metrics.get("avg_loss")
    payoff = (
        round(abs(float(avg_win) / float(avg_loss)), 4)
        if avg_win and avg_loss
        else None
    )
    sorted_pnls = sorted(pnls)
    tail_n = max(1, len(sorted_pnls) // 20)
    return {
        "n": len(pnls),
        "n_losses": int(metrics.get("n_losses") or 0),
        "expectancy": metrics.get("expectancy"),
        "profit_factor": metrics.get("profit_factor"),
        "win_rate": metrics.get("win_rate"),
        "payoff": payoff,
        "tail_loss_p05": (
            round(sum(sorted_pnls[:tail_n]) / tail_n, 5) if sorted_pnls else None
        ),
        "max_drawdown_pips": _max_drawdown_pips(pnls),
        "bootstrap_p05": _mean_lower_95(pnls),
    }


def hierarchical_strategy_selection(
    records: list[dict],
    *,
    cost_by_symbol: dict[str, float],
    shortlist_frac: float = 0.6,
    min_shortlist_n: int = 20,
    min_validate_n: int = 10,
    min_symbols_pool: int = 3,
    max_candidates: int = 200,
) -> dict[str, Any]:
    """Hierarchical SYMBOL-AWARE validation (P3).

    LEVEL A: symbol + regime + structure + session + side + strategy_family(setup)
    LEVEL B: symbol + regime + structure + session + side
    LEVEL C: cross-symbol pooled state, ONLY when every participating symbol
             individually clears its own cost-adjusted sanity check.

    A profitable pooled Asia SELL can no longer make every pair eligible to
    sell: each symbol must earn its own place, and pooling requires
    demonstrated homogeneity.
    """
    import collections

    state_keys = ("regime", "structure", "session", "side")
    records = sorted(records, key=lambda r: str(r.get("bar_time") or ""))
    cut = int(len(records) * shortlist_frac)
    early, late = records[:cut], records[cut:]

    def cost_of(symbol: str) -> float:
        return float(cost_by_symbol.get(str(symbol).upper(), 10.0))  # unknown: prohibitive

    def collect(frame: list[dict], keys: tuple[str, ...]) -> dict[tuple, list[dict]]:
        grouped: dict[tuple, list[dict]] = {}
        for r in frame:
            k = tuple(str(r.get(key) or "") for key in keys)
            grouped.setdefault(k, []).append(r)
        return grouped

    def matches_state(r: dict, state: dict) -> bool:
        return all(str(r.get(k) or "") == v for k, v in state.items())

    opportunities: list[dict[str, Any]] = []

    # ---- LEVEL A: symbol+state+family ----
    level_a: dict[tuple, dict[str, Any]] = {}
    for sig, rows in collect(early, ("symbol", *state_keys, "setup")).items():
        symbol = sig[0]
        train_pnls = _costed([float(r["outcome"]) for r in rows], cost_of(symbol))
        if len(train_pnls) < min_shortlist_n:
            continue
        m = _state_metrics(train_pnls)
        if (m["expectancy"] or 0) > 0:
            level_a[sig] = {"train": m, "dominant_family": str(sig[5] or "")}

    # ---- LEVEL B: symbol+state ----
    level_b: dict[tuple, dict[str, Any]] = {}
    for sig, rows in collect(early, ("symbol", *state_keys)).items():
        symbol = sig[0]
        train_pnls = _costed([float(r["outcome"]) for r in rows], cost_of(symbol))
        if len(train_pnls) < min_shortlist_n:
            continue
        m = _state_metrics(train_pnls)
        if (m["expectancy"] or 0) > 0:
            families = collections.Counter(str(r.get("setup") or "") for r in rows)
            dominant_family = families.most_common(1)[0][0] if families else ""
            a_entry = level_a.get((symbol, *sig[1:], dominant_family))
            level_b[sig] = {
                "train": m,
                "dominant_family": dominant_family,
                "family_confirmed": bool(a_entry),
                "families": dict(families.most_common(5)),
            }

    # ---- validate LEVEL A/B on the late (OOS) window ----
    for level, table in (("A", level_a), ("B", level_b)):
        for sig, info in table.items():
            symbol = sig[0]
            # LEVEL A sigs are (symbol, *state_keys, setup): the state part is
            # still exactly the 4 state keys; setup rides along as sig[5].
            state = dict(zip(state_keys, sig[1:1 + len(state_keys)]))
            late_rows = [
                r for r in late
                if str(r.get("symbol") or "") == symbol and matches_state(r, state)
            ]
            if level == "A":
                # Defect 6: LEVEL A trains on symbol+state+FAMILY, so the OOS
                # window must test the SAME family; mixing setups contaminates
                # family validation.
                family = str(info.get("dominant_family") or "")
                late_rows = [
                    r for r in late_rows
                    if str(r.get("setup") or "") == family
                ]
            late_pnls = _costed([float(r["outcome"]) for r in late_rows], cost_of(symbol))
            if len(late_pnls) < min_validate_n:
                continue
            vm = _state_metrics(late_pnls)
            gate_ok, gate_reason = oos_gate(vm)
            opportunities.append({
                "level": level,
                "symbol": symbol,
                **state,
                "strategy_family": info.get("dominant_family", ""),
                "family_confirmed": info.get("family_confirmed", False),
                "families": info.get("families"),
                "cost_pips": cost_of(symbol),
                "n_train": info["train"]["n"],
                "expectancy_train": info["train"]["expectancy"],
                "n_validate": vm["n"],
                "n_losses_validate": vm["n_losses"],
                "expectancy_validate": vm["expectancy"],
                "profit_factor_validate": vm["profit_factor"],
                "win_rate_validate": vm["win_rate"],
                "payoff_validate": vm["payoff"],
                "tail_loss_p05_validate": vm["tail_loss_p05"],
                "max_drawdown_pips_validate": vm["max_drawdown_pips"],
                "bootstrap_p05_validate": vm["bootstrap_p05"],
                "gate_reason": gate_reason,
                "survives_validate": bool(gate_ok),
            })

    # ---- LEVEL C: pooled state with per-symbol homogeneity proof ----
    for sig, rows in collect(early, state_keys).items():
        state = dict(zip(state_keys, sig))
        by_symbol: dict[str, list[float]] = {}
        for r in rows:
            by_symbol.setdefault(str(r.get("symbol") or ""), []).append(float(r["outcome"]))
        qualified_symbols = []
        homogeneous = True
        for symbol, pnls in sorted(by_symbol.items()):
            net = _costed(pnls, cost_of(symbol))
            if len(net) < min_shortlist_n:
                continue
            m = _state_metrics(net)
            if (m["expectancy"] or 0) > 0:
                qualified_symbols.append(symbol)
            else:
                homogeneous = False
        if len(qualified_symbols) < min_symbols_pool or not homogeneous:
            continue
        pool_late = [
            r for r in late
            if str(r.get("symbol") or "") in qualified_symbols and matches_state(r, state)
        ]
        pooled_net = [
            float(r["outcome"]) - cost_of(str(r.get("symbol") or "")) for r in pool_late
        ]
        if len(pooled_net) < min_validate_n * min_symbols_pool:
            continue
        vm = _state_metrics(pooled_net)
        pool_gate_ok, pool_gate_reason = oos_gate(vm)
        for symbol in qualified_symbols:
            sym_late = [
                float(r["outcome"]) - cost_of(str(r.get("symbol") or ""))
                for r in pool_late
                if str(r.get("symbol") or "") == symbol
            ]
            # Defect 7: pooled survival is NOT inheritable by itself. Each
            # symbol must independently clear the same OOS sanity gates on its
            # own late-window outcomes before it receives the opportunity.
            sym_vm = _state_metrics(sym_late) if sym_late else {"n": 0}
            sym_ok, sym_reason = oos_gate(sym_vm)
            opportunities.append({
                "level": "C",
                "symbol": symbol,
                **state,
                "strategy_family": "*pooled*",
                "pool_symbols": qualified_symbols,
                "pool_homogeneous": True,
                "cost_pips": cost_of(symbol),
                "n_train_pool": sum(len(v) for v in by_symbol.values()),
                "n_validate_pool": vm["n"],
                "expectancy_validate_pool": vm["expectancy"],
                "profit_factor_validate_pool": vm["profit_factor"],
                "bootstrap_p05_validate_pool": vm["bootstrap_p05"],
                "pool_gate_reason": pool_gate_reason,
                "n_validate_symbol": sym_vm.get("n", 0),
                "n_losses_validate_symbol": sym_vm.get("n_losses"),
                "expectancy_validate_symbol": sym_vm.get("expectancy"),
                "profit_factor_validate_symbol": sym_vm.get("profit_factor"),
                "payoff_validate_symbol": sym_vm.get("payoff"),
                "bootstrap_p05_validate_symbol": sym_vm.get("bootstrap_p05"),
                "symbol_gate_reason": sym_reason,
                "survives_validate": bool(pool_gate_ok and sym_ok),
            })

    # Dedupe: LEVEL A records are family-scoped and all stay visible; B/C
    # collapse per (symbol, state) with A > B > C preference.
    best: dict[tuple, dict[str, Any]] = {}
    rank = {"A": 3, "B": 2, "C": 1}
    for opp in opportunities:
        if opp["level"] == "A":
            best[(
                opp["symbol"], opp["regime"], opp["structure"], opp["session"],
                opp["side"], "A", str(opp.get("strategy_family") or ""),
            )] = opp
            continue
        key = (opp["symbol"], opp["regime"], opp["structure"], opp["session"], opp["side"])
        cur = best.get(key)
        cur_ev = (
            float(cur.get("expectancy_validate") or cur.get("expectancy_validate_pool") or -1e9)
            if cur else -1e9
        )
        opp_ev = float(opp.get("expectancy_validate") or opp.get("expectancy_validate_pool") or -1e9)
        if cur is None or rank[opp["level"]] > rank[cur["level"]] or (
            rank[opp["level"]] == rank[cur["level"]] and opp_ev > cur_ev
        ):
            best[key] = opp
    final = sorted(
        best.values(),
        key=lambda o: float(o.get("expectancy_validate") or o.get("expectancy_validate_pool") or -1e9),
        reverse=True,
    )[:max_candidates]
    survivors = [o for o in final if o["survives_validate"]]
    return {
        "shortlist_frac": float(shortlist_frac),
        "n_level_a_states": len(level_a),
        "n_level_b_states": len(level_b),
        "n_opportunities": len(final),
        "n_survive": len(survivors),
        "opportunities": final,
    }


def write_validated_opportunities(
    selection: dict[str, Any],
    *,
    dataset_hash: str,
    config_hash: str,
    code_version: str,
    cost_model: dict[str, Any],
    path: Path = INTEL_DIR / "validated_opportunities.json",
) -> Path:
    """Persist the auditable validated-opportunity artifact (P13).

    A clean clone can reproduce exactly what is allowed, from which dataset,
    which config, which code version, and why each record was accepted.
    """
    survivors = [o for o in selection.get("opportunities", []) if o.get("survives_validate")]
    payload = {
        "schema": "validated_opportunities.v1",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "code_version": code_version,
        "dataset_hash": dataset_hash,
        "config_hash": config_hash,
        "cost_model": cost_model,
        "n_opportunities": len(survivors),
        "opportunities": survivors,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


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


def write_demo_canary(
    opportunity: dict[str, Any],
    *,
    dataset_hash: str,
    index_file_sha256: str,
    risk_fraction: float,
    path: Path = INTEL_DIR / "demo_canary.json",
    validity_days: float = 7.0,
) -> Path | None:
    """Defect 16: a DEMO_CANARY permission artifact tied to ONE validated
    opportunity. No artifact => no canary orders; the research bootstrap stays
    shadow-only. Expires unless regenerated from fresh validation."""
    if not opportunity or not opportunity.get("survives_validate"):
        if path.exists():
            path.unlink()
        return None
    metrics = {
        k: opportunity.get(k) for k in (
            "expectancy_validate", "profit_factor_validate",
            "bootstrap_p05_validate", "n_validate", "n_losses_validate")
        if opportunity.get(k) is not None
    }
    payload = {
        "schema": "demo_canary.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "expires_utc": (datetime.now(timezone.utc) + timedelta(days=validity_days)).isoformat(),
        "strategy_id": "canary_" + "_".join(
            str(opportunity.get(k, "")) for k in ("symbol", "regime", "structure", "session", "side")
        ),
        "opportunity": {
            k: opportunity.get(k)
            for k in ("level", "symbol", "regime", "structure", "session", "side",
                      "strategy_family", "cost_pips")
        },
        "metrics": metrics,
        "dataset_hash": dataset_hash,
        "validation_hash": hashlib.sha256(
            json.dumps(metrics, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
        "index_file_sha256": index_file_sha256,
        "risk_fraction": float(risk_fraction),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def ml_advances(absolute_expectancy: float | None, improvement: float | None) -> bool:
    """Defect 10: relative improvement is NOT success.

    An ML model may only advance when its ABSOLUTE costed out-of-sample
    expectancy is > 0. A positive improvement over a negative baseline while
    still net-negative is a failed candidate, permanently.
    """
    if absolute_expectancy is None:
        return False
    return float(absolute_expectancy) > 0.0


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
    # Audited remediation 1: proper predictor protocol replaces the old
    # auto-top-50% scorer. Threshold learned on inner walk-forward only;
    # sealed holdout evaluated once; ml_advances recomputed from evidence.
    from aegis.research.predictor_protocol import run_predictor_protocol

    meta_cols = [c for c in ("symbol", "side", "session", "regime",
                             "strategy_family") if c in df.columns]
    ml = run_predictor_protocol(
        df,
        holdout_frac=0.3,
        n_folds=4,
        min_trades_threshold=50,
        meta=df[meta_cols] if meta_cols else None,
    )
    ml["train_n"] = ml.get("train_n", 0)
    ml["holdout_n"] = ml.get("sealed_n", 0)
    ml["n_taken"] = (ml.get("sealed_taken") or {}).get("n") or 0
    all_ev = (ml.get("sealed_all") or {}).get("expectancy")
    taken_exp = (ml.get("sealed_taken") or {}).get("expectancy")
    ml.setdefault("all_holdout_expectancy", all_ev)
    ml.setdefault("model_taken_expectancy", taken_exp)
    ml["all_holdout"] = {"expectancy": all_ev}
    ml["model_taken"] = {"expectancy": taken_exp}
    ml["improvement_expectancy"] = round(
        (taken_exp or 0.0) - (all_ev or 0.0), 5)
    from aegis.research.predictor_protocol import ml_advances_from_protocol

    ml["ml_advances"] = ml_advances_from_protocol(ml)

    from aegis.research.exit_research import per_trade_cost_pips

    sample_cost = per_trade_cost_pips(symbols[0], float(pip_by_symbol.get(symbols[0], 0.0001)), spread_bps, slippage_bps) if symbols else 0.0
    commission_rt = float(cfg.get("commission_round_trip_usd", 0.0) or 0.0)

    # P4/defect 9: measured per-symbol/session cost profiles override the
    # config formula wherever journal evidence is sufficient.
    cost_model = symbol_cost_pips(
        pip_by_symbol,
        spread_bps=spread_bps,
        slippage_bps=slippage_bps,
        commission_round_trip_usd=commission_rt,
    )
    cost_by_symbol = {s: m["cost_pips"] for s, m in cost_model.items()}
    profiles_path = resolve_bot_path(
        cfg.get("cost_profiles_path"), INTEL_DIR / "cost_profiles.json"
    )
    try:
        profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
        for sym, prof in (profiles.get("symbols") or {}).items():
            measured = prof.get("validation_cost_pips")
            if measured:
                cost_by_symbol[str(sym).upper()] = float(measured)
                cost_model.setdefault(str(sym).upper(), {})["measured_cost_pips"] = float(measured)
                cost_model[str(sym).upper()]["cost_source"] = prof.get("cost_source")
    except (OSError, json.JSONDecodeError):
        pass  # no profiles yet: formula costs remain the documented fallback

    # P3/P13: hierarchical symbol-aware selection with reproducible hashes.
    import hashlib
    import subprocess as _sp

    dataset_hash = hashlib.sha256(
        "\n".join(
            json.dumps(r, sort_keys=True, default=str)
            for r in sorted(records, key=lambda r: (str(r.get("symbol")), str(r.get("bar_time"))))
        ).encode("utf-8")
    ).hexdigest()
    config_hash = hashlib.sha256(
        json.dumps(
            {
                "spread_bps": spread_bps,
                "slippage_bps": slippage_bps,
                "commission_round_trip_usd": commission_rt,
                "shortlist_frac": 0.6,
                "min_shortlist_n": 20,
                "min_validate_n": 10,
                "min_symbols_pool": 3,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    try:
        code_version = _sp.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(BOT)
        ).stdout.strip() or "unknown"
    except Exception:
        code_version = "unknown"

    hier = hierarchical_strategy_selection(records, cost_by_symbol=cost_by_symbol)
    opportunities_path = write_validated_opportunities(
        hier,
        dataset_hash=dataset_hash,
        config_hash=config_hash,
        code_version=code_version,
        cost_model=cost_model,
        path=resolve_bot_path(
            cfg.get("validated_opportunities_path"),
            INTEL_DIR / "validated_opportunities.json",
        ),
    )
    # Defect 16: DEMO_CANARY permission artifact for the single best survivor,
    # bound to dataset + validation hashes. No survivor => artifact removed.
    index_file = resolve_bot_path(cfg.get("analogue_index_path"), INTEL_DIR / "analogue_index.json")
    try:
        index_file_sha = hashlib.sha256(index_file.read_bytes()).hexdigest()
    except OSError:
        index_file_sha = ""
    survivors_all = [o for o in hier.get("opportunities", []) if o.get("survives_validate")]
    canary_path = write_demo_canary(
        survivors_all[0] if survivors_all else {},
        dataset_hash=dataset_hash,
        index_file_sha256=index_file_sha,
        risk_fraction=float(cfg.get("intelligent_risk_fraction", 0.08) or 0.08),
        path=resolve_bot_path(cfg.get("demo_canary_path"), INTEL_DIR / "demo_canary.json"),
    )
    # Legacy pooled-state allowlist: only LEVEL C survivors qualify.
    pooled_survivors = [
        {**{k: o.get(k) for k in ("regime", "structure", "session", "side")},
         **{m: o.get(m) for m in (
             "n_validate_pool", "expectancy_validate_pool",
             "profit_factor_validate_pool", "bootstrap_p05_validate_pool")}}
        for o in hier.get("opportunities", [])
        if o.get("level") == "C" and o.get("survives_validate")
    ]
    validated_states_path = write_validated_states(
        {"validated": [{"survives_validate": bool(s.get("bootstrap_p05_validate_pool") and s["bootstrap_p05_validate_pool"] > 0), **s} for s in pooled_survivors]},
        path=resolve_bot_path(
            cfg.get("validated_states_path"), INTEL_DIR / "validated_states.json"
        ),
    )
    selection = {
        "n_shortlisted": hier.get("n_level_b_states"),
        "n_validated": hier.get("n_opportunities"),
        "n_survive": hier.get("n_survive"),
        "cost_model": cost_model,
        "hierarchical": True,
    }

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
        "hierarchical_selection": {
            "n_level_a_states": hier.get("n_level_a_states"),
            "n_level_b_states": hier.get("n_level_b_states"),
            "n_opportunities": hier.get("n_opportunities"),
            "n_survive": hier.get("n_survive"),
        },
        "dataset_hash": dataset_hash,
        "config_hash": config_hash,
        "code_version": code_version,
        "validated_opportunities_path": str(opportunities_path),
        "validated_states_path": str(validated_states_path),
        "ml": {
            "train_n": ml["train_n"],
            "holdout_n": ml["holdout_n"],
            "n_taken": ml["n_taken"],
            "all_holdout_expectancy": ml["all_holdout"]["expectancy"],
            "model_taken_expectancy": ml["model_taken"]["expectancy"],
            "improvement_expectancy": ml["improvement_expectancy"],
            "ml_advances": ml["ml_advances"],
            "locked_threshold": ml.get("locked_threshold"),
            "threshold_source": ml.get("threshold_source"),
            "correlation_pearson": ml.get("correlation_pearson"),
            "correlation_spearman": ml.get("correlation_spearman"),
            "mae": ml.get("mae"),
            "rmse": ml.get("rmse"),
            "monotonicity_fraction": ml.get("monotonicity_fraction"),
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