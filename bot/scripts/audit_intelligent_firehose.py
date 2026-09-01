#!/usr/bin/env python3
"""Aggregate journals/artifacts into the intelligent-firehose failure audit."""
from __future__ import annotations

import json
import collections
import statistics
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
REPORTS = BOT / "reports"
INTEL = BOT / "intel"


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def pct(values, q):
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(q * len(s))))
    return round(s[idx], 4)


def summarize_pnls(pnls):
    n = len(pnls)
    if not n:
        return {"n": 0}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gp = sum(wins)
    gl = abs(sum(losses))
    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n, 4),
        "gross_profit": round(gp, 2),
        "gross_loss": round(gl, 2),
        "profit_factor": round(gp / gl, 4) if gl > 0 else None,
        "expectancy": round(sum(pnls) / n, 5),
        "net": round(sum(pnls), 2),
        "avg_win": round(gp / len(wins), 4) if wins else None,
        "avg_loss": round(-gl / len(losses), 4) if losses else None,
        "tail_loss_5pct": pct(losses, 0.05) if losses else None,
    }


def main() -> int:
    audit: dict = {
        "schema": "intelligent_firehose_failure_audit.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "head": None,
    }
    try:
        import subprocess
        audit["head"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(BOT.parent)
        ).stdout.strip()
    except Exception:
        pass

    # ---- heartbeat / risk / research artifacts ----
    hb = load_json(REPORTS / "bot_heartbeat.json") or {}
    risk = load_json(REPORTS / "risk_state.json") or {}
    ol = load_json(REPORTS / "research" / "outcome_learning.json") or {}
    ml = load_json(REPORTS / "research" / "ml_pipeline.json") or {}
    vs = load_json(INTEL / "validated_states.json") or {}
    champ = load_json(INTEL / "champion.json")
    ichamp = load_json(INTEL / "intelligent_champion.json")
    current_best = load_json(REPORTS / "research" / "current_best.md")

    audit["runtime"] = {
        "heartbeat": {k: hb.get(k) for k in (
            "pid", "status", "brain", "equity", "open", "fire", "scale", "reduce",
            "exit", "skip", "quote_stale", "validated_states", "gate_validated_states",
            "champion")},
        "risk_state": {k: risk.get(k) for k in (
            "halted", "permanent_halt", "peak_equity", "day_start_equity", "reason")},
        "validated_states_artifact": {
            "schema": vs.get("schema"), "built_at": vs.get("built_at"),
            "n_survive": vs.get("n_survive"), "states": vs.get("states"),
            "path_exists": (INTEL / "validated_states.json").exists(),
        },
        "champion_artifact": None if not champ else {
            "id": champ.get("id"), "decision": champ.get("decision"),
            "expectancy": champ.get("expectancy"), "profit_factor": champ.get("profit_factor"),
            "updated_utc": champ.get("updated_utc")},
        "intelligent_champion_artifact": ichamp,
        "outcome_learning_summary": {
            k: ol.get(k) for k in ("total_trades", "win_rate", "profit_factor",
                                   "expectancy_r", "payoff_ratio", "breakeven_win_rate")
            if isinstance(ol, dict)},
        "ml_pipeline_strategy_selection": {
            k: (ml.get("strategy_selection") or {}).get(k)
            for k in ("n_shortlisted", "n_validated", "n_survive", "cost_pips_assumed")},
    }

    # ---- journal aggregation ----
    jr = REPORTS / "mt5_demo_firehose_hw_journal.jsonl"
    brain_skip_reasons = collections.Counter()
    intel_skip_reasons = collections.Counter()
    order_results = collections.Counter()
    order_reject_reasons = collections.Counter()
    oms_rejects = collections.Counter()
    open_skips = collections.Counter()
    sizing_skips = collections.Counter()
    halts = collections.Counter()
    flatten_reasons = collections.Counter()
    quote_stale_ages = []
    quote_future_skews = []
    spreads_by_symbol = collections.defaultdict(list)
    fire_events = 0
    scale_events = 0
    reduce_events = 0
    exit_events = 0
    first_ts = last_ts = None
    fires_by_symbol_side = collections.Counter()

    for row in iter_jsonl(jr):
        ev = row.get("event")
        ts = row.get("bar") or row.get("ts")
        if isinstance(ts, str):
            first_ts = first_ts or ts
            last_ts = ts
        if ev == "intel_brain_skip":
            brain_skip_reasons[str(row.get("reason"))] += 1
        elif ev == "intel_skip":
            intel_skip_reasons[str(row.get("reason"))] += 1
        elif ev == "order":
            ok = bool(row.get("ok"))
            order_results["ok" if ok else "rejected"] += 1
            if not ok:
                order_reject_reasons[str(row.get("msg") or row.get("reason"))[:120]] += 1
        elif ev == "oms_reject":
            oms_rejects[str(row.get("reason"))[:120]] += 1
        elif ev == "open_skip":
            open_skips[str(row.get("reason"))[:80]] += 1
        elif ev == "sizing_skip":
            sizing_skips[str(row.get("reason"))[:80]] += 1
        elif ev == "halt":
            halts[str(row.get("reason"))[:100]] += 1
        elif ev == "flatten":
            flatten_reasons[str(row.get("reason"))[:60]] += 1
        elif ev == "quote_stale":
            try:
                quote_stale_ages.append(float(row.get("age_s")))
            except (TypeError, ValueError):
                pass
        elif ev == "quote_future":
            try:
                quote_future_skews.append(float(row.get("skew_s")))
            except (TypeError, ValueError):
                pass
        elif ev == "spread_skip":
            sym = row.get("symbol")
            try:
                spreads_by_symbol[sym].append(float(row.get("spread")))
            except (TypeError, ValueError):
                pass
        elif ev == "intel_brain_fire":
            fire_events += 1
            fires_by_symbol_side[(row.get("symbol"), row.get("side"))] += 1
        elif ev == "intel_brain_scale":
            scale_events += 1
        elif ev == "intel_brain_reduce":
            reduce_events += 1
        elif ev == "intel_brain_exit":
            exit_events += 1

    total_decisions = (
        fire_events + scale_events + reduce_events + exit_events
        + sum(brain_skip_reasons.values())
    )
    audit["journal_window"] = {"first_bar": first_ts, "last_bar": last_ts}
    audit["decisions"] = {
        "fire": fire_events,
        "scale": scale_events,
        "reduce": reduce_events,
        "exit": exit_events,
        "brain_skip_total": sum(brain_skip_reasons.values()),
        "skip_rate": round(sum(brain_skip_reasons.values()) / total_decisions, 4)
        if total_decisions else None,
        "brain_skip_reasons": dict(brain_skip_reasons.most_common(40)),
        "intel_skip_reasons": dict(intel_skip_reasons.most_common(20)),
    }
    audit["execution"] = {
        "orders_ok": order_results["ok"],
        "orders_rejected": order_results["rejected"],
        "order_reject_reasons": dict(order_reject_reasons.most_common(20)),
        "oms_rejects": dict(oms_rejects.most_common(20)),
        "oms_reject_total": sum(oms_rejects.values()),
        "open_skip_reasons": dict(open_skips.most_common(15)),
        "sizing_skip_reasons": dict(sizing_skips.most_common(10)),
        "halts": dict(halts.most_common(10)),
        "flatten_reasons": dict(flatten_reasons.most_common(15)),
    }
    audit["quotes"] = {
        "stale_events": len(quote_stale_ages),
        "stale_age_median_s": statistics.median(quote_stale_ages) if quote_stale_ages else None,
        "stale_age_p95": pct(quote_stale_ages, 0.95),
        "future_events": len(quote_future_skews),
        "future_skew_median_s": statistics.median(quote_future_skews) if quote_future_skews else None,
        "future_skew_max": max(quote_future_skews) if quote_future_skews else None,
    }
    audit["spread_skip"] = {
        "by_symbol_top": {s: len(v) for s, v in sorted(
            spreads_by_symbol.items(), key=lambda kv: -len(kv[1]))[:30]},
        "spread_median_by_symbol": {s: round(statistics.median(v), 5) for s, v in
                                    spreads_by_symbol.items()},
    }
    audit["fires_by_symbol_side"] = {
        f"{s}|{side}": c for (s, side), c in fires_by_symbol_side.most_common(30)}

    # ---- realized outcomes from mt5 deals ----
    deals = {}
    for row in iter_jsonl(INTEL / "outcome_log.jsonl"):
        if row.get("source") not in {"mt5_deal", "reconcile"}:
            continue
        ticket = str(row.get("position") or row.get("ticket"))
        if row.get("is_exit"):
            deals[ticket] = row
    by_symbol = collections.defaultdict(list)
    by_side = collections.defaultdict(list)
    by_close = collections.defaultdict(list)
    all_pnls = []
    for row in deals.values():
        try:
            pnl = float(row.get("pnl"))
        except (TypeError, ValueError):
            continue
        sym = str(row.get("symbol"))
        side = str(row.get("side"))
        close = str(row.get("close_reason"))
        by_symbol[sym].append(pnl)
        by_side[side].append(pnl)
        by_close[close].append(pnl)
        all_pnls.append(pnl)

    audit["realized"] = {
        "closed_trades": len(all_pnls),
        "overall": summarize_pnls(all_pnls),
        "by_symbol": {s: summarize_pnls(v) for s, v in sorted(by_symbol.items())},
        "by_side": {s: summarize_pnls(v) for s, v in sorted(by_side.items())},
        "by_close_reason": {s: summarize_pnls(v) for s, v in sorted(by_close.items())},
    }

    out_dir = REPORTS / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "intelligent_firehose_failure_audit.json").write_text(
        json.dumps(audit, indent=2, default=str), encoding="utf-8")

    # ---- markdown ----
    md = [
        "# Intelligent Firehose Failure Audit",
        f"_generated {audit['generated_utc']} | HEAD {audit['head']}_",
        "",
        "## Runtime snapshot",
        "",
    ]
    rt = audit["runtime"]
    md.append(f"- heartbeat: `{json.dumps(rt['heartbeat'], default=str)}`")
    md.append(f"- risk_state: `{json.dumps(rt['risk_state'], default=str)}`")
    md.append(f"- validated states artifact: `{json.dumps(rt['validated_states_artifact'], default=str)[:400]}`")
    md.append(f"- champion artifact: `{json.dumps(rt['champion_artifact'], default=str)}`")
    md.append(f"- intelligent champion present: `{bool(rt['intelligent_champion_artifact'])}`")
    md.append(f"- ml_pipeline strategy_selection: `{json.dumps(rt['ml_pipeline_strategy_selection'])}`")
    md += ["", "## Decision distribution", ""]
    dec = audit["decisions"]
    md.append(f"- window: {audit['journal_window']['first_bar']} -> {audit['journal_window']['last_bar']}")
    md.append(f"- FIRE {dec['fire']} | SCALE {dec['scale']} | REDUCE {dec['reduce']} | EXIT {dec['exit']} | BRAIN_SKIP {dec['brain_skip_total']} (skip rate {dec['skip_rate']})")
    md.append("")
    md.append("### brain skip reasons")
    md.append("")
    md.append("| reason | count |")
    md.append("|---|---|")
    for r, c in list(dec["brain_skip_reasons"].items())[:25]:
        md.append(f"| {r} | {c} |")
    md += ["", "## Execution", ""]
    ex = audit["execution"]
    md.append(f"- orders ok {ex['orders_ok']} / rejected {ex['orders_rejected']}; oms_reject total {ex['oms_reject_total']}")
    md.append(f"- top order reject reasons: `{json.dumps(dict(list(ex['order_reject_reasons'].items())[:8]))}`")
    md.append(f"- top oms rejects: `{json.dumps(dict(list(ex['oms_rejects'].items())[:8]))}`")
    md.append(f"- halts: `{json.dumps(ex['halts'])}`")
    md.append(f"- flatten reasons: `{json.dumps(dict(list(ex['flatten_reasons'].items())[:10]))}`")
    md += ["", "## Quotes", ""]
    md.append(f"- stale events {audit['quotes']['stale_events']} (median age {audit['quotes']['stale_age_median_s']}s, p95 {audit['quotes']['stale_age_p95']}s)")
    md.append(f"- future-quote events {audit['quotes']['future_events']} (median skew {audit['quotes']['future_skew_median_s']}s, max {audit['quotes']['future_skew_max']}s)")
    md += ["", "## Spread skips by symbol (top)", ""]
    for s, c in list(audit["spread_skip"]["by_symbol_top"].items())[:15]:
        med = audit["spread_skip"]["spread_median_by_symbol"].get(s)
        md.append(f"- {s}: {c} skips, median spread at skip {med}")
    md += ["", "## Fires by symbol|side (top)", ""]
    for k, c in list(audit["fires_by_symbol_side"].items())[:15]:
        md.append(f"- {k}: {c}")
    md += ["", "## Realized outcomes (MT5 deals)", ""]
    real = audit["realized"]
    md.append(f"- closed trades {real['closed_trades']}; overall `{json.dumps(real['overall'])}`")
    md.append("")
    md.append("### by symbol")
    md.append("")
    md.append("| symbol | n | WR | PF | expectancy | net |")
    md.append("|---|---|---|---|---|---|")
    for s, m in real["by_symbol"].items():
        md.append(f"| {s} | {m.get('n')} | {m.get('win_rate')} | {m.get('profit_factor')} | {m.get('expectancy')} | {m.get('net')} |")
    md.append("")
    md.append("### by side")
    md.append("")
    for s, m in real["by_side"].items():
        md.append(f"- {s}: `{json.dumps(m)}`")
    md.append("")
    md.append("### by close reason")
    md.append("")
    for s, m in real["by_close_reason"].items():
        md.append(f"- {s}: `{json.dumps(m)}`")
    (out_dir / "intelligent_firehose_failure_audit.md").write_text("\n".join(md), encoding="utf-8")
    print("wrote", out_dir / "intelligent_firehose_failure_audit.md")
    print(json.dumps({
        "decisions": {k: dec[k] for k in ("fire", "scale", "reduce", "exit", "brain_skip_total", "skip_rate")},
        "top_brain_skips": dict(list(dec["brain_skip_reasons"].items())[:8]),
        "overall_realized": real["overall"],
        "orders": {k: ex[k] for k in ("orders_ok", "orders_rejected", "oms_reject_total")},
        "quotes": {k: audit["quotes"][k] for k in ("stale_events", "future_events")},
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
