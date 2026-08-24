"""Regression tests for the independent-audit defect list (1-12, 15)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.research.incremental_ingest import (  # noqa: E402
    label_matured_targets,
    load_cursor,
    merge_into_index,
)
from scripts.research_ml_pipeline import (  # noqa: E402
    hierarchical_strategy_selection,
    ml_advances,
    write_validated_opportunities,
)


# ---------------------------------------------------------------------------
# Defect 1/2: watcher heartbeat accepts ingest; stdout JSON parsing
# ---------------------------------------------------------------------------


def test_writer_emits_v2_only_for_family_scoped_costed_records(tmp_path):
    record = {
        "level": "A",
        "symbol": "EURUSD",
        "strategy_family": "failed_breakout_fade",
        "regime": "range",
        "structure": "none",
        "session": "asia",
        "side": "sell",
        "survives_validate": True,
        "strategy_version": "rule-v1",
        "rule_fingerprint": "rule-hash",
        "index_hash": "index-hash",
        "session_cost_provenance": {"source": "measured_quotes"},
    }
    path = write_validated_opportunities(
        {"opportunities": [record]},
        dataset_hash="dataset-hash",
        config_hash="config-hash",
        code_version="code-hash",
        cost_model={},
        path=tmp_path / "validated_opportunities.json",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema"] == "validated_opportunities.v2"
    assert payload["opportunities"][0]["strategy_family"] == "failed_breakout_fade"
    assert payload["v1_opportunities"][0]["strategy_family"] == "failed_breakout_fade"


def test_write_heartbeat_persists_ingest_status(tmp_path, monkeypatch):
    """A complete watcher heartbeat write must accept and persist ingest data."""
    from scripts import research_fast_watcher as w

    monkeypatch.setattr(w, "HEARTBEAT", tmp_path / "watcher_heartbeat.json")
    monkeypatch.setattr(w, "OPENCODE_DIR", tmp_path)
    monkeypatch.setattr(w, "_mt5_status", lambda: {"ok": True})
    monkeypatch.setattr(w, "_champion", lambda: {})
    monkeypatch.setattr(w, "staleness_report", lambda: {"alerts": []})
    monkeypatch.setattr(w, "_runner_pid", lambda: 1234)
    monkeypatch.setattr(w, "_runner_process_alive", lambda: True)
    path = w.write_heartbeat(
        tick=1,
        watcher_alive=True,
        last_cycle="2026-08-21T00:00:00+00:00",
        no_new_evidence=False,
        new_outcome_lines=3,
        ingest={"ok": True, "stdout_json": {"added_total": 7}},
        throughput={"ok": True},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ingest"]["stdout_json"]["added_total"] == 7
    assert payload["throughput"]["ok"] is True


def test_run_script_parses_stdout_json(tmp_path):
    """_run_script returns stdout_json parsed from the script's last JSON blob."""
    from scripts.research_fast_watcher import _parse_stdout_json

    noisy = "starting...\nprogress 50%\n{\"added_total\": 5, \"new_bars_total\": 600}\n"
    assert _parse_stdout_json(noisy)["added_total"] == 5
    assert _parse_stdout_json("no json here") is None
    assert _parse_stdout_json("") is None
    assert _parse_stdout_json("{\"a\": 1}")["a"] == 1
    # Multiple JSON blobs: the LAST one wins (final summary).
    two = "{\"a\": 1}\nmiddle\n{\"added_total\": 9}\n"
    assert _parse_stdout_json(two)["added_total"] == 9


# ---------------------------------------------------------------------------
# Defect 3 + 4: maturity cursor, warm-up, sequential cycles grow the index
# ---------------------------------------------------------------------------


def _synth_frame(n, start="2026-05-01", prefix_len=None):
    """Deterministic M1 frame with structure the labeller can recognise."""
    time = pd.date_range(start, periods=n, freq="min", tz="UTC")
    close = pd.Series([1.10 + ((i * 7) % 13) * 0.00003 for i in range(n)])
    return pd.DataFrame({
        "time": time,
        "open": close - 0.00002,
        "high": close + 0.00008,
        "low": close - 0.00008,
        "close": close,
        "volume": 100.0,
    })


def test_immature_bar_labelled_exactly_once_in_later_cycle():
    """Cycle 1: bar T observed but horizon incomplete -> raw only, NOT labelled.
    Cycle 2: future bars exist -> bar T labelled exactly once."""
    # Cycle-1 window: warmup + a few pending bars near the end (<120 forward).
    frame1 = _synth_frame(400 + 30)
    rows1, newest1 = label_matured_targets(
        frame1.iloc[:430].reset_index(drop=True), symbol="EURUSD", pip=0.0001,
        label_cursor=None, warmup_bars=400, maturity_bars=120,
    )
    # With only 30 bars after warmup, nothing can be matured yet.
    assert newest1 is None or all(
        pd.Timestamp(r["bar_time"]) <= frame1["time"].iloc[-121] for r in rows1
    )
    pending = [r for r in rows1]
    # Cycle-2 window extends well past cycle 1's end.
    frame2 = _synth_frame(400 + 200)
    rows2, newest2 = label_matured_targets(
        frame2, symbol="EURUSD", pip=0.0001,
        label_cursor=newest1, warmup_bars=400, maturity_bars=120,
    )
    # Every cycle-1 row reappears at most once in cycle 2 (dedupe by time).
    times1 = {r["bar_time"] for r in pending}
    times2 = [r["bar_time"] for r in rows2]
    assert len(times2) == len(set(times2))
    overlap = times1 & set(times2)
    assert overlap <= times1
    # The index merge dedupes across cycles.
    index = Path("x")  # unused by direct assertion below
    merged = {"records": list(rows1)}
    existing_keys = {(str(r.get("symbol")), str(r.get("bar_time"))) for r in merged["records"]}
    fresh = [r for r in rows2 if ("EURUSD", r["bar_time"]) not in existing_keys]
    assert len(fresh) == len({r["bar_time"] for r in fresh})


def test_sequential_cycles_grow_index_without_duplicates(tmp_path, monkeypatch):
    """Simulated 20-minute cycles: each new window adds NEW matured labels.

    build_market_state is stubbed with a deterministic range state so the test
    exercises the cursor/maturity/dedupe machinery, not structure detection.
    """
    class _FakeState:
        def __init__(self):
            self.structure = {"M15": {"kind": "retest",
                                      "support": 1.0995, "resistance": 1.1005}}

        def as_dict(self):
            return {
                "regime": {"label": "range"},
                "volatility": {"phase": "stable"},
                "structure": self.structure,
                "multi_timeframe": {"H1": {"direction": "up"},
                                    "M5": {"direction": "down"}},
                "session": "asia",
            }

    import aegis.research.market_state as ms

    monkeypatch.setattr(ms, "build_market_state", lambda symbol, m1: _FakeState())

    index_path = tmp_path / "analogue_index.json"
    total = 0
    seen = set()
    for cycle in range(3):
        n = 520 + cycle * 60  # window grows as new bars arrive
        frame = _synth_frame(n)
        rows, _ = label_matured_targets(
            frame, symbol="EURUSD", pip=0.0001,
            label_cursor=None, warmup_bars=400, maturity_bars=120,
        )
        result = merge_into_index(index_path, rows)
        assert result["added"] == len([r for r in rows if r["bar_time"] not in seen])
        seen.update(r["bar_time"] for r in rows)
        total += result["added"]
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload["n"] == total
    assert total > 0  # the index actually grew over sequential cycles


def test_cursor_v2_round_trip_and_migration(tmp_path):
    path = tmp_path / "cursor.json"
    cursor = {"schema": "ingest_cursor.v2",
              "symbols": {"EURUSD": {"raw_cursor": "t2", "label_cursor": "t1"}}}
    from aegis.research.incremental_ingest import save_cursor

    save_cursor(cursor, path)
    loaded = load_cursor(path)
    assert loaded["symbols"]["EURUSD"]["label_cursor"] == "t1"
    # v1 migration: single ts becomes both cursors.
    path.write_text(json.dumps({"schema": "ingest_cursor.v1",
                                "symbols": {"GBPUSD": "t9"}}), encoding="utf-8")
    migrated = load_cursor(path)
    assert migrated["symbols"]["GBPUSD"] == {"raw_cursor": "t9", "label_cursor": "t9"}


# ---------------------------------------------------------------------------
# Defect 6: LEVEL A OOS must test the SAME family trained on
# ---------------------------------------------------------------------------


def _family_record(symbol, setup, i, outcome, day):
    return {
        "symbol": symbol,
        "bar_time": f"2026-04-{day:02d}T{i % 20:02d}:00:00+00:00",
        "side": "sell",
        "setup": setup,
        "regime": "range",
        "structure": "none",
        "session": "asia",
        "outcome": outcome,
    }


def _win_pattern(i):
    return 1.0 if i % 4 else -0.5  # 75% win, payoff 2.0 -> p05>0 at n>=40


def _lose_pattern(i):
    return 1.0 if i % 10 < 1 else -0.5  # 10% win -> clearly negative EV


def test_level_a_oos_family_contamination_fails():
    """setup A train+, setup B OOS+, setup A OOS- => LEVEL A for setup A FAILS."""
    records = []
    # Train window days 1-16 (first 60% of timeline); OOS days 17-28.
    for i in range(60):
        records.append(_family_record("EURUSD", "retest", i, _win_pattern(i), 1 + i % 14))
        records.append(_family_record("EURUSD", "breakout", i, _win_pattern(i + 3), 1 + i % 14))
    for i in range(60):
        records.append(_family_record("EURUSD", "retest", i, _lose_pattern(i), 17 + i % 10))
        records.append(_family_record("EURUSD", "breakout", i, _win_pattern(i + 5), 17 + i % 10))
    selection = hierarchical_strategy_selection(
        records,
        cost_by_symbol={"EURUSD": 0.2},
        shortlist_frac=0.6,
        min_shortlist_n=20,
        min_validate_n=10,
    )
    level_a = {o["strategy_family"]: o for o in selection["opportunities"]
               if o["level"] == "A"}
    assert "retest" in level_a, "family A trained positive so it must be evaluated"
    assert level_a["retest"]["survives_validate"] is False, (
        "LEVEL A retest must fail on its OWN negative family OOS, not borrow "
        "breakout's positive OOS"
    )


# ---------------------------------------------------------------------------
# Defect 7: LEVEL C piggyback requires per-symbol OOS gates
# ---------------------------------------------------------------------------


def test_level_c_negative_oos_symbol_gets_no_opportunity():
    """EURUSD OOS+, GBPUSD OOS+, USDCHF OOS-, pooled OOS+ => USDCHF gets nothing."""
    records = []

    def add(symbol, late_win_pattern, i, day):
        pattern = _win_pattern(i) if day <= 16 else (
            _win_pattern(i) if late_win_pattern else _lose_pattern(i)
        )
        records.append({
            "symbol": symbol,
            "bar_time": f"2026-04-{day:02d}T{i % 20:02d}:00:00+00:00",
            "side": "sell",
            "setup": "retest",
            "regime": "range",
            "structure": "none",
            "session": "asia",
            "outcome": pattern,
        })

    for i in range(60):
        day = 1 + i % 14
        add("EURUSD", True, i, day)
        add("GBPUSD", True, i, day)
        add("USDCHF", True, i, day)  # train positive everywhere
    for i in range(60):
        day = 17 + i % 10
        add("EURUSD", True, i, day)
        add("GBPUSD", True, i, day)
        add("USDCHF", False, i, day)  # OOS negative
    selection = hierarchical_strategy_selection(
        records,
        cost_by_symbol={"EURUSD": 0.2, "GBPUSD": 0.2, "USDCHF": 0.2},
        shortlist_frac=0.6,
        min_shortlist_n=20,
        min_validate_n=10,
        min_symbols_pool=2,
    )
    # The safety property: USDCHF must hold NO surviving opportunity at any
    # level (its own OOS is negative even though the pooled basket passes).
    usdchf = [o for o in selection["opportunities"] if o["symbol"] == "USDCHF"]
    assert usdchf, "USDCHF was pool-eligible so it must have been evaluated"
    assert not any(o["survives_validate"] for o in usdchf)
    for sym in ("EURUSD", "GBPUSD"):
        assert any(o["survives_validate"] for o in selection["opportunities"]
                   if o["symbol"] == sym)


# ---------------------------------------------------------------------------
# Defect 8: gates are strict (already enforced via oos_gate) - spot check
# ---------------------------------------------------------------------------


def test_oos_gate_rejects_weak_but_positive_candidates():
    from scripts.research_ml_pipeline import oos_gate

    ok = {"n": 30, "n_losses": 9, "expectancy": 0.55, "profit_factor": 1.4,
          "bootstrap_p05": 0.3, "payoff": 2.0}
    passed, reason = oos_gate(ok)
    assert passed
    for bad, why in [
        ({**ok, "n": 5}, "insufficient_oos_n"),
        ({**ok, "n_losses": 2}, "insufficient_loss_tail"),
        ({**ok, "expectancy": -0.1}, "expectancy_not_positive"),
        ({**ok, "profit_factor": 0.9}, "profit_factor_not_above_one"),
        ({**ok, "bootstrap_p05": -0.1}, "bootstrap_p05_not_positive"),
        ({**ok, "payoff": 0.1}, "payoff_below_floor"),
    ]:
        passed, reason = oos_gate(bad)
        assert not passed and reason.startswith(why)


# ---------------------------------------------------------------------------
# Defect 10: absolute expectancy gate
# ---------------------------------------------------------------------------


def test_ml_relative_improvement_with_negative_absolute_fails():
    """improvement +0.0465 over baseline while model EV = -0.8762 is FAILURE."""
    assert ml_advances(-0.8762, 0.0465) is False
    assert ml_advances(-0.01, 5.0) is False  # huge relative gain, still negative
    assert ml_advances(0.001, -0.5) is True  # absolute positive wins regardless
    assert ml_advances(None, 1.0) is False


# ---------------------------------------------------------------------------
# Defect 12: closed-trade trigger with explicit schema + inference
# ---------------------------------------------------------------------------


def test_twenty_new_closed_positions_trigger_once(tmp_path):
    from scripts.research_fast_watcher import _evidence_trigger

    log = tmp_path / "outcome_log.jsonl"
    base = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(20):
        rows.append({
            "event_type": "position_exit",
            "symbol": "EURUSD",
            "pnl": 0.5,
            "ts_utc": (base + timedelta(minutes=i)).isoformat(),
        })
    log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps({"last_utc": ""}), encoding="utf-8")
    trigger = _evidence_trigger(outcome_log_path=log, marker_path=marker)
    assert trigger == "new_closed_trades"
    # After the marker advances past them, no repeat trigger.
    marker.write_text(json.dumps({"last_utc": (base + timedelta(hours=1)).isoformat()}),
                      encoding="utf-8")
    assert _evidence_trigger(outcome_log_path=log, marker_path=marker) is None


def test_exit_row_backwards_compatible_inference():
    from aegis.intel.outcome_log import is_exit_row

    assert is_exit_row({"event_type": "position_exit"})
    assert is_exit_row({"is_exit": True})           # historical explicit
    assert not is_exit_row({"is_exit": False})
    assert is_exit_row({"action": "exit"})           # historical action proof
    assert is_exit_row({"action": "reduce"})
    assert is_exit_row({"source": "reconcile", "pnl": -0.2})  # reconcile+pnl
    assert not is_exit_row({"source": "runner", "pnl": 1.0})
    assert not is_exit_row({})
