"""Read-only ingest of live journal/heartbeat/deals. Never places orders."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROTECTED_LIVE_YAML = "config_mt5_demo_firehose_hw.yaml"
PHASE0_EVIDENCE = "docs/superpowers/evidence/2026-08-15-phase-0-baseline.md"

# Sealed Phase 0 snapshot (measured 2026-08-15). Replaced by live ingest when files exist.
PHASE0_MEASURED = {
    "journal_spread_skips": 20756,
    "journal_orders": 3402,
    "journal_ok": 861,
    "journal_fail": 2541,
    "journal_10019": 2252,
    "flatten_n": 616,
    "flatten_wr": 0.373,
    "flatten_e": -0.0135,
    "flatten_pf": 0.61,
    "deals_n": 989,
    "deals_wr": 0.421,
    "deals_e": -0.043,
    "deals_pf": 0.34,
    "deals_net": -42.60,
}


def read_json(path: Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def ingest_live_state(
    *,
    heartbeat_path: Path,
    risk_path: Path,
    journal_path: Path | None = None,
    deals_path: Path | None = None,
) -> dict[str, Any]:
    hb = read_json(heartbeat_path)
    risk = read_json(risk_path)
    observed: dict[str, Any] = dict(PHASE0_MEASURED)
    observed["source"] = PHASE0_EVIDENCE
    observed["phase0_deals_n"] = PHASE0_MEASURED["deals_n"]
    observed["phase0_deals_wr"] = PHASE0_MEASURED["deals_wr"]
    observed["phase0_deals_e"] = PHASE0_MEASURED["deals_e"]
    observed["phase0_deals_pf"] = PHASE0_MEASURED["deals_pf"]
    observed["phase0_deals_net"] = PHASE0_MEASURED["deals_net"]
    if journal_path and Path(journal_path).is_file():
        from aegis.research.costs import cost_book_from_journal

        jbook = cost_book_from_journal(Path(journal_path))
        observed["journal_spread_skips"] = jbook.get("n_spread_skip")
        observed["journal_orders"] = jbook.get("n_orders")
        observed["journal_ok"] = jbook.get("n_ok")
        observed["journal_fail"] = int(jbook.get("n_orders") or 0) - int(jbook.get("n_ok") or 0)
        observed["journal_10019"] = jbook.get("n_no_money")
        observed["source"] = str(journal_path)
    if deals_path and Path(deals_path).is_file():
        from aegis.research.costs import cost_book_from_deals

        dbook = cost_book_from_deals(Path(deals_path))
        observed["deals_n"] = dbook.get("n")
        observed["deals_wr"] = dbook.get("win_rate")
        observed["deals_e"] = dbook.get("expectancy")
        observed["deals_pf"] = dbook.get("profit_factor")
        observed["deals_net"] = dbook.get("net_pnl")
        observed["deals_n_raw"] = dbook.get("n_raw")
        observed["deals_deduped_by"] = dbook.get("deduped_by")
        observed["deals_source"] = str(deals_path)
    return {
        "equity": hb.get("equity"),
        "open": hb.get("open"),
        "held": hb.get("held") or [],
        "risk_halted": bool(hb.get("risk_halted") or risk.get("halted")),
        "risk_reason": hb.get("risk_reason") or risk.get("reason") or "",
        "permanent_halt": bool(risk.get("permanent_halt")),
        "circuit_ok": hb.get("circuit_ok"),
        "quote_stale": hb.get("quote_stale"),
        "pid": hb.get("pid"),
        "journal_path": str(journal_path) if journal_path else None,
        "observed": observed,
        "mt5_touched": False,
        "placed_orders": False,
        "live_yaml_writable": False,
        "protected_yaml": PROTECTED_LIVE_YAML,
    }
