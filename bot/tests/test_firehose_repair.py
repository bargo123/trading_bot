"""P3/P4/P8/P9/P14 regression tests: symbol-aware validation, costs, send
guards, incremental ingestion, thesis-keyed memory, throughput aggregation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.intel.send_guard import (  # noqa: E402
    estimate_margin,
    margin_precheck_ok,
    min_lot_ok,
    needs_quote_refresh,
    refresh_verdict,
)
from aegis.research.incremental_ingest import (  # noqa: E402
    load_cursor,
    merge_into_index,
    save_cursor,
)
from scripts.research_ml_pipeline import (  # noqa: E402
    hierarchical_strategy_selection,
    symbol_cost_pips,
)


# ---------------------------------------------------------------------------
# P8: stale quote refresh + pre-send guards
# ---------------------------------------------------------------------------


def test_stale_quote_requires_refresh_not_disabled_protection():
    assert needs_quote_refresh(6.0, max_age_s=5.0)
    assert not needs_quote_refresh(1.0, max_age_s=5.0)
    assert not needs_quote_refresh(99.0, max_age_s=0.0)  # protection off = config error path


def test_failed_refresh_prevents_order():
    verdict = refresh_verdict(new_age_s=9.0, new_spread=0.0002, max_age_s=5.0, max_spread=0.001)
    assert not verdict.ok
    assert verdict.reason == "refresh_still_stale"
    widened = refresh_verdict(new_age_s=0.2, new_spread=0.02, max_age_s=5.0, max_spread=0.001)
    assert not widened.ok
    assert widened.reason == "spread_widened_beyond_max"
    good = refresh_verdict(new_age_s=0.2, new_spread=0.0002, max_age_s=5.0, max_spread=0.001)
    assert good.ok


def test_margin_precheck_blocks_no_money_orders():
    # Historical failure mode: 2679x "10019 No money".
    est = estimate_margin(price=1.10, lots=0.01, contract_size=100000, leverage=100)
    assert est == pytest.approx(11.0)
    assert not margin_precheck_ok(5.0, est)
    assert margin_precheck_ok(50.0, est)
    # Unknown funds defer to broker-side protection rather than blocking all.
    assert margin_precheck_ok(None, est)


def test_min_lot_guard_blocks_sub_minimum_quantity():
    assert not min_lot_ok(0.01, 0.1)
    assert min_lot_ok(0.1, 0.1)
    assert min_lot_ok(0.01, 0.0)  # no minimum known


# ---------------------------------------------------------------------------
# P4: per-symbol cost model
# ---------------------------------------------------------------------------


def test_per_symbol_costs_differ_across_pip_conventions():
    costs = symbol_cost_pips(
        {"EURUSD": 0.0001, "USDJPY": 0.01, "GBPJPY": 0.01},
        spread_bps=1.0,
        slippage_bps=0.5,
        commission_round_trip_usd=7.0,
    )
    eur = costs["EURUSD"]
    jpy = costs["USDJPY"]
    gbp = costs["GBPJPY"]
    # bps normalize pip conventions: identical bps -> identical spread pips.
    assert eur["spread_pips"] == pytest.approx(jpy["spread_pips"])
    # Commission expressed in pips DIFFERS because pip value differs per symbol.
    assert eur["commission_pips"] > jpy["commission_pips"]
    assert gbp["cost_pips"] == pytest.approx(
        gbp["spread_pips"] + gbp["slippage_pips"] + gbp["commission_pips"]
    )
    # A zero-commission config must not add phantom cost.
    free = symbol_cost_pips({"EURUSD": 0.0001}, spread_bps=1.0, slippage_bps=0.5)
    assert free["EURUSD"]["commission_pips"] == 0.0


def test_symbol_aware_cost_can_invalidate_globally_attractive_state():
    """P14-11: a state attractive at EURUSD's cost fails at a wide-spread symbol."""
    def rec(symbol, side, i):
        return {
            "symbol": symbol,
            "bar_time": f"2026-01-{(i % 28) + 1:02d}T{i % 24:02d}:00:00+00:00",
            "side": side,
            "setup": "retest",
            "regime": "range",
            "structure": "retest",
            "session": "asia",
            "outcome": 3.0 if i % 3 else -1.0,
        }

    records = []
    for i in range(120):
        records.append(rec("EURUSD", "sell", i))
        records.append(rec("GBPNZD", "sell", i))  # wide-spread cross
    selection = hierarchical_strategy_selection(
        records,
        cost_by_symbol={"EURUSD": 0.3, "GBPNZD": 4.0},
        shortlist_frac=0.6,
        min_shortlist_n=20,
        min_validate_n=10,
    )
    survivors = {o["symbol"] for o in selection["opportunities"] if o["survives_validate"]}
    # The cheap symbol can survive; the expensive one must not piggyback.
    assert "EURUSD" in survivors or not survivors
    assert "GBPNZD" not in survivors


# ---------------------------------------------------------------------------
# P3: hierarchical symbol-aware validation
# ---------------------------------------------------------------------------


def _state_record(symbol, regime, session, side, i, outcome):
    return {
        "symbol": symbol,
        "bar_time": f"2026-02-{(i % 28) + 1:02d}T{(i % 20):02d}:00:00+00:00",
        "side": side,
        "setup": "retest",
        "regime": regime,
        "structure": "none",
        "session": session,
        "outcome": outcome,
    }


def test_profitable_pooled_state_does_not_autopilot_every_symbol():
    """P14-9/10: pooling requires per-symbol evidence; contradicting symbols are
    rejected, and only qualifying symbols receive the LEVEL C opportunity."""
    records = []
    # Two symbols with genuinely positive Asia-sell outcomes...
    for i in range(160):
        records.append(_state_record("EURUSD", "range", "asia", "sell", i, 2.5 if i % 2 else -0.5))
        records.append(_state_record("AUDUSD", "range", "asia", "sell", i, 2.0 if i % 2 else -0.5))
    # ...and one that contradicts the pooled thesis.
    for i in range(160):
        records.append(_state_record("GBPJPY", "range", "asia", "sell", i, -2.0))
    selection = hierarchical_strategy_selection(
        records,
        cost_by_symbol={"EURUSD": 0.3, "AUDUSD": 0.3, "GBPJPY": 0.8},
        shortlist_frac=0.6,
        min_shortlist_n=20,
        min_validate_n=10,
        min_symbols_pool=2,
    )
    opps = [o for o in selection["opportunities"] if o.get("level") == "C" and o["survives_validate"]]
    symbols = {o["symbol"] for o in opps}
    assert "GBPJPY" not in symbols
    pool_records = [o for o in opps if o["symbol"] in {"EURUSD", "AUDUSD"}]
    for o in pool_records:
        assert set(o["pool_symbols"]) <= {"EURUSD", "AUDUSD"}


def test_level_b_beats_pooled_when_symbol_specific_evidence_exists():
    records = []
    for i in range(200):
        records.append(_state_record("EURUSD", "trend", "asia", "sell", i, 3.0 if i % 2 else -0.5))
    selection = hierarchical_strategy_selection(
        records,
        cost_by_symbol={"EURUSD": 0.3},
        shortlist_frac=0.6,
        min_shortlist_n=20,
        min_validate_n=10,
        min_symbols_pool=3,  # impossible with one symbol -> no fake pooling
    )
    levels = {o["level"] for o in selection["opportunities"]}
    assert "C" not in levels


# ---------------------------------------------------------------------------
# P9: incremental ingestion is restart-safe and dedupes
# ---------------------------------------------------------------------------


def test_cursor_round_trip(tmp_path):
    cursor = {"schema": "ingest_cursor.v1", "symbols": {"EURUSD": "2026-03-01T00:00:00+00:00"}}
    path = save_cursor(cursor, tmp_path / "cursor.json")
    loaded = load_cursor(path)
    assert loaded["symbols"]["EURUSD"].startswith("2026-03-01")


def test_merge_into_index_dedupes_on_restart(tmp_path):
    index = tmp_path / "analogue_index.json"
    rows = [
        {"symbol": "EURUSD", "bar_time": "2026-03-01T00:00:00+00:00", "outcome": 1.0},
        {"symbol": "EURUSD", "bar_time": "2026-03-01T00:01:00+00:00", "outcome": -1.0},
    ]
    first = merge_into_index(index, rows)
    assert first["added"] == 2
    second = merge_into_index(index, rows)  # same data again: restart safety
    assert second["added"] == 0
    third = merge_into_index(index, [dict(rows[0], bar_time="2026-03-01T00:02:00+00:00")])
    assert third["added"] == 1
    payload = json.loads(index.read_text(encoding="utf-8"))
    assert payload["n"] == 3


# ---------------------------------------------------------------------------
# P6: thesis-keyed memory
# ---------------------------------------------------------------------------


def test_two_independent_theses_coexist_on_one_symbol():
    from aegis.intel.firehose_brain import DemoBrainState

    state = DemoBrainState()
    long_key = "EURUSD|buy|retest|range|asia"
    short_key = "EURUSD|sell|breakout|range|asia"
    state.apply("EURUSD", "fire", side="buy", information_id="info-l",
                target_risk=1.0, setup_family="retest", regime="range", session="asia")
    state.apply("EURUSD", "fire", side="sell", information_id="info-s",
                target_risk=1.0, setup_family="breakout", regime="range", session="asia")
    assert state.get(long_key).current_risk_usd == 1.0
    assert state.get(short_key).current_risk_usd == 1.0
    # Exiting one thesis leaves the other intact.
    state.apply("EURUSD", "exit", side="buy", information_id=None,
                target_risk=0.0, setup_family="retest", regime="range", session="asia")
    assert state.get(long_key).current_risk_usd == 0.0
    assert state.get(short_key).current_risk_usd == 1.0


def test_two_same_side_theses_own_distinct_tickets():
    """Defect 15: two independent EURUSD BUY theses each own distinct positions;
    closing/reducing thesis A must not mutate thesis B."""
    from aegis.intel.firehose_brain import DemoBrainState

    class _Pos:
        def __init__(self, symbol, side, ticket):
            self.symbol = symbol
            self.side = side
            self.ticket = ticket
            self.unrealized_pnl = 0.0

    state = DemoBrainState()
    key_a = "EURUSD|buy|retest|range|asia"
    key_b = "EURUSD|buy|breakout|trend|london"
    state.apply("EURUSD", "fire", side="buy", information_id="a1",
                target_risk=1.0, key=key_a)
    state.apply("EURUSD", "fire", side="buy", information_id="b1",
                target_risk=1.0, key=key_b)
    state.bind_tickets(key_a, "EURUSD", ["101", "102"])
    state.bind_tickets(key_b, "EURUSD", ["201"])
    positions = [_Pos("EURUSD", "buy", "101"), _Pos("EURUSD", "buy", "102"),
                 _Pos("EURUSD", "buy", "201")]
    state.sync_from_positions("EURUSD", positions, clip_risk=0.5)
    assert state.get(key_a).clips == 2
    assert state.get(key_b).clips == 1
    # Close thesis A's tickets only: B keeps its clip and risk.
    state.apply("EURUSD", "exit", side="buy", information_id=None,
                target_risk=0.0, key=key_a)
    remaining = [p for p in positions if p.ticket != "101" and p.ticket != "102"]
    state.sync_from_positions("EURUSD", remaining, clip_risk=0.5)
    mem_b = state.get(key_b)
    assert mem_b.clips == 1
    assert mem_b.current_risk_usd > 0
    assert mem_b.information_id == "b1"
    # Ticket rebinding cannot steal: binding 201 to A removes it from B.
    state.bind_tickets(key_a, "EURUSD", ["201"])
    assert "201" not in state.get(key_b).tickets
    assert "201" in state.get(key_a).tickets


class _Pos:
    def __init__(self, symbol, side, ticket=""):
        self.symbol = symbol
        self.side = side
        self.ticket = ticket
        self.unrealized_pnl = 0.0


def test_sync_from_positions_adopts_and_clears_theses():
    from aegis.intel.firehose_brain import DemoBrainState

    state = DemoBrainState()
    key = "EURUSD|sell|retest|range|asia"
    state.apply("EURUSD", "fire", side="sell", information_id="s1",
                target_risk=1.0, key=key)
    state.bind_tickets(key, "EURUSD", ["501"])
    touched = state.sync_from_positions("EURUSD", [_Pos("EURUSD", "sell", "501")], clip_risk=0.5)
    sell = [m for m in touched if m.side == "sell" and m.tickets][0]
    assert sell.clips == 1
    # Position gone upstream -> thesis cleared.
    state.sync_from_positions("EURUSD", [], clip_risk=0.5)
    assert state.get(key).clips == 0
    # Unknown position adopted under held-key so exposure is never lost.
    touched = state.sync_from_positions("EURUSD", [_Pos("EURUSD", "buy", "601")], clip_risk=0.5)
    assert any(m.side == "buy" and m.clips == 1 for m in touched)


# ---------------------------------------------------------------------------
# P7: throughput aggregation
# ---------------------------------------------------------------------------


def test_throughput_report_counts_skip_reasons(tmp_path):
    from scripts.firehose_throughput import main as tp_main

    journal = tmp_path / "journal.jsonl"
    rows = [
        {"event": "intel_brain_skip", "reason": "no_validated_strategy_model", "symbol": "EURUSD", "bar": "2026-08-19T23:30:00+00:00"},
        {"event": "intel_brain_skip", "reason": "shadow:not_trading_stage:UNVALIDATED_RESEARCH", "symbol": "GBPJPY", "bar": "2026-08-20T08:00:00+00:00"},
        {"event": "intel_brain_fire", "symbol": "EURUSD", "side": "sell", "bar": "2026-08-20T09:00:00+00:00"},
        {"event": "order", "ok": True, "msg": "", "symbol": "EURUSD"},
        {"event": "order", "ok": False, "msg": "10019 No money", "symbol": "EURUSD"},
        {"event": "margin_precheck_skip", "symbol": "XAUUSD"},
    ]
    journal.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "throughput.json"
    rc = tp_main.__wrapped__() if hasattr(tp_main, "__wrapped__") else None
    # call via argparse-free path: monkeypatch defaults through direct invocation
    import sys as _sys

    _sys.argv = ["firehose_throughput.py", "--journal", str(journal), "--out", str(out)]
    assert tp_main() == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["scanned_opportunities"] == 3
    assert report["decisions"]["skip"] == 2
    assert report["decisions"]["fire"] == 1
    assert report["skip_reason_distribution"]["no_validated_strategy_model"] == 1
    assert report["orders_sent"] == 2
    assert report["executed"] == 1
    assert report["pretrade_guards"]["margin_precheck_skip"] == 1


def test_brain_intent_does_not_count_as_broker_fire():
    from scripts.firehose_throughput import aggregate_funnel

    report = aggregate_funnel([{"event": "intel_brain_fire", "submitted": False}])

    assert {
        "SCANS", "MICRO_CANDIDATES", "BOOK_SUPPORTED", "VALIDATED_MATCH",
        "EXPLORATION_ELIGIBLE", "SPREAD_REJECT", "ECONOMICS_REJECT",
        "GEOMETRY_REJECT", "RISK_REJECT", "STALE_REJECT", "OTHER_REJECT",
        "FIRES", "FILLS",
    } <= report.keys()
    assert report["FIRES"] == 0


def test_margin_rejection_is_a_risk_terminal_outcome():
    from scripts.firehose_throughput import aggregate_funnel

    report = aggregate_funnel([{"event": "margin_precheck_skip"}])

    assert report["RISK_REJECT"] == 1
    assert report["FIRES"] == 0
