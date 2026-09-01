"""Optimizer unit tests: lock, experiment round-trip, accept gate, snapshot fallback."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import dump_config, load_config
from aegis.optimizer.experiment import (
    accept_experiment,
    apply_patch,
    reject_experiment,
    start_experiment,
)
from aegis.optimizer.metrics import compute_trade_metrics
from aegis.optimizer.paths import OPTIMIZER_LOCK, PAPER_LOCK
from aegis.optimizer.snapshot import collect_snapshot
from aegis.optimizer.walk_forward import accept_gate, chronological_split, walk_forward_slices
from aegis.paper_control import ProcessLock


def _patch_optimizer_home(monkeypatch, home: Path) -> None:
    lock = home / "optimizer.lock"
    monkeypatch.setattr("aegis.optimizer.paths.OPTIMIZER_DIR", home)
    monkeypatch.setattr("aegis.optimizer.paths.OPTIMIZER_LOCK", lock)
    for mod in (
        "aegis.optimizer.state",
        "aegis.optimizer.experiment",
        "aegis.optimizer.snapshot",
        "aegis.optimizer.knowledge",
        "aegis.optimizer.promote",
        "aegis.optimizer.status",
        "aegis.optimizer.cycle",
    ):
        monkeypatch.setattr(f"{mod}.OPTIMIZER_DIR", home, raising=False)
    monkeypatch.setattr("aegis.optimizer.cycle.OPTIMIZER_LOCK", lock, raising=False)


def test_optimizer_lock_is_not_the_paper_lock():
    assert OPTIMIZER_LOCK.resolve() != PAPER_LOCK.resolve()


def test_process_lock_try_acquire_conflict(tmp_path: Path):
    path = tmp_path / "opt.lock"
    first = ProcessLock(path)
    second = ProcessLock(path)
    assert first.try_acquire()
    assert not second.try_acquire()
    first.release()
    assert second.try_acquire()
    second.release()


def test_apply_patch_top_level_and_dotted():
    cfg = {"firehose_tp_pips": 1, "nested": {"a": 1}}
    out = apply_patch(cfg, {"firehose_tp_pips": 2, "nested.a": 9})
    assert cfg["firehose_tp_pips"] == 1
    assert out["firehose_tp_pips"] == 2
    assert out["nested"]["a"] == 9


def test_metrics_from_synthetic_trades():
    trades = [
        {"pnl": 1.0},
        {"pnl": 1.0},
        {"pnl": -2.0},
        {"pnl": 0.5},
    ]
    m = compute_trade_metrics(trades, starting_equity=100.0)
    assert m["total_trades"] == 4
    assert m["wins"] == 3
    assert m["losses"] == 1
    assert abs(m["win_rate"] - 75.0) < 1e-9
    assert abs(m["net_pnl"] - 0.5) < 1e-9
    assert m["max_consecutive_wins"] == 2
    assert m["max_consecutive_losses"] == 1
    assert m["expectancy"] == 0.125


def test_accept_gate_tharp_and_dd():
    base = {"expectancy_r": 0.10, "max_drawdown_pct": 5.0, "win_rate": 60.0, "total_trades": 40}
    better = {"expectancy_r": 0.20, "max_drawdown_pct": 5.5, "win_rate": 55.0, "total_trades": 40}
    ok, _ = accept_gate(base, better, min_trades=20, dd_tolerance_pct=2.0)
    assert ok
    wr_up_e_down = {"expectancy_r": 0.05, "max_drawdown_pct": 4.0, "win_rate": 90.0, "total_trades": 40}
    ok, reason = accept_gate(base, wr_up_e_down, min_trades=20, dd_tolerance_pct=2.0)
    assert not ok
    assert "expectancy" in reason.lower()
    fat_dd = {"expectancy_r": 0.50, "max_drawdown_pct": 20.0, "win_rate": 50.0, "total_trades": 40}
    ok, reason = accept_gate(base, fat_dd, min_trades=20, dd_tolerance_pct=2.0)
    assert not ok
    assert "DD" in reason or "drawdown" in reason.lower()
    weak_base = {"expectancy_r": 0.001, "max_drawdown_pct": 5.0, "win_rate": 50.0, "total_trades": 40}
    noisy_win = {"expectancy_r": 0.002, "max_drawdown_pct": 5.0, "win_rate": 55.0, "total_trades": 40}
    ok, reason = accept_gate(
        weak_base, noisy_win, min_trades=20, dd_tolerance_pct=2.0, stored_best_e=0.029
    )
    assert not ok
    assert "stored best" in reason.lower()
    ok, _ = accept_gate(base, better, min_trades=20, dd_tolerance_pct=2.0, stored_best_e=0.029)
    assert ok


def test_research_overlay_rejects_synthetic_and_negative_e():
    from aegis.optimizer.research_gate import research_overlay_gate

    positive = {
        "expectancy_r": 0.05,
        "profit_factor": 1.2,
        "total_trades": 40,
        "net_pnl": 1.0,
        "win_rate": 40.0,
    }
    ok, reason = research_overlay_gate(positive, data_source="synthetic")
    assert not ok
    assert "synthetic" in reason.lower()
    ok, reason = research_overlay_gate(
        {
            "expectancy_r": -0.01,
            "profit_factor": 0.9,
            "total_trades": 40,
            "net_pnl": -0.4,
            "win_rate": 95.0,
        },
        data_source="mt5_bars",
    )
    assert not ok
    assert "expectancy" in reason.lower()
    ok, reason = research_overlay_gate(positive, data_source="mt5_bars")
    assert ok


def test_core_1_30_does_not_use_foreign_stored_best():
    from aegis.optimizer.cycle import _stored_best_for_gate

    assert _stored_best_for_gate({"firehose_tp_pips": 1, "firehose_sl_pips": 30}) is None
    # Non-CORE TP/SL may still consult stored best (returns None only if no file).
    got = _stored_best_for_gate({"firehose_tp_pips": 3, "firehose_sl_pips": 25})
    assert got is None or isinstance(got, float)


def test_walk_forward_slices_expanding():
    slices = walk_forward_slices(200, folds=3)
    assert len(slices) == 3
    assert slices[0][0] == slice(0, 50)
    is_df, oos_df = chronological_split(
        __import__("pandas").DataFrame({"x": range(10)}), 0.7
    )
    assert len(is_df) == 7
    assert len(oos_df) == 3


def test_snapshot_fallback_without_mt5(tmp_path: Path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    journal = reports / "mt5_demo_firehose_hw_journal.jsonl"
    journal.write_text(
        json.dumps({"event": "flatten", "symbol": "GBPUSD", "pnl": 0.12, "reason": "max_hold"})
        + "\n"
        + json.dumps({"event": "spread_skip", "symbol": "EURAUD"})
        + "\n",
        encoding="utf-8",
    )
    (reports / "bot_heartbeat.json").write_text(
        json.dumps({"ts": 1.0, "open": 0, "equity": 94.4, "status": "running"}),
        encoding="utf-8",
    )
    home = tmp_path / "optimizer"
    home.mkdir()
    _patch_optimizer_home(monkeypatch, home)
    monkeypatch.setattr("aegis.optimizer.snapshot.REPORTS_DIR", reports)
    monkeypatch.setattr("aegis.optimizer.snapshot.HEARTBEAT", reports / "bot_heartbeat.json")
    monkeypatch.setattr("aegis.optimizer.paths.REPORTS_DIR", reports)
    cfg = {
        "test_name": "mt5_demo_firehose_hw",
        "algo": "firehose",
        "symbol": "GBPUSD",
        "starting_equity": 100,
    }
    snap = collect_snapshot(cfg, no_mt5=True, persist=True, reports_dir=reports)
    assert snap["mt5_ok"] is False
    assert snap["spread_skips"] == 1
    assert snap["metrics"]["total_trades"] == 1
    assert (home / "metrics" / "latest.json").exists()


def test_experiment_accept_and_reject_revert(tmp_path: Path, monkeypatch):
    _patch_optimizer_home(monkeypatch, tmp_path)
    src = tmp_path / "accepted.yaml"
    dump_config(
        {
            "symbol": "GBPUSD",
            "timeframe": "1m",
            "mode": "mt5_demo",
            "firehose_tp_pips": 1,
        },
        src,
    )
    rec = start_experiment(
        exp_id="exp_test_widen",
        accepted_src=src,
        patch={"firehose_tp_pips": 2},
        meta={"hypothesis": "widen tp"},
    )
    cand = load_config(tmp_path / "candidate.yaml")
    assert cand["firehose_tp_pips"] == 2
    rejected = reject_experiment(rec, {"expectancy_r": -0.1}, "worse OOS")
    assert rejected["decision"] == "reject"
    reverted = load_config(tmp_path / "candidate.yaml")
    assert reverted["firehose_tp_pips"] == 1

    rec2 = start_experiment(
        exp_id="exp_test_accept",
        accepted_src=src,
        patch={"firehose_tp_pips": 3},
        meta={"hypothesis": "accept me"},
    )
    accepted = accept_experiment(rec2, {"expectancy_r": 0.2}, bot_open=2)
    assert accepted["decision"] == "accept"
    assert accepted["pending_promote"] is True
    assert load_config(tmp_path / "accepted.yaml")["firehose_tp_pips"] == 3
    pending = json.loads((tmp_path / "pending_promote.json").read_text(encoding="utf-8"))
    assert pending["experiment_id"] == "exp_test_accept"


def test_promote_noop_when_open(tmp_path: Path, monkeypatch):
    from aegis.optimizer.promote import promote_if_flat

    _patch_optimizer_home(monkeypatch, tmp_path)
    accepted = tmp_path / "accepted.yaml"
    live = tmp_path / "live.yaml"
    dump_config({"symbol": "GBPUSD", "timeframe": "1m", "mode": "mt5_demo"}, accepted)
    dump_config({"symbol": "GBPUSD", "timeframe": "1m", "mode": "mt5_demo", "firehose_tp_pips": 1}, live)
    monkeypatch.setattr(
        "aegis.optimizer.promote.load_heartbeat",
        lambda path=None: {"open": 3, "pid": 1},
    )
    result = promote_if_flat(live_config=live, accepted=accepted, restart=False)
    assert result["promoted"] is False
    assert result["open"] == 3
    assert (tmp_path / "pending_promote.json").exists()
    assert load_config(live)["firehose_tp_pips"] == 1
    pending = json.loads((tmp_path / "pending_promote.json").read_text(encoding="utf-8"))
    pending["experiment_id"] = "exp_keep_me"
    (tmp_path / "pending_promote.json").write_text(json.dumps(pending), encoding="utf-8")
    again = promote_if_flat(live_config=live, accepted=accepted, restart=False)
    assert again["promoted"] is False
    kept = json.loads((tmp_path / "pending_promote.json").read_text(encoding="utf-8"))
    assert kept["experiment_id"] == "exp_keep_me"
    assert kept["open"] == 3


def test_consumed_ids_skip_accepted_widen_tp(tmp_path: Path, monkeypatch):
    from aegis.optimizer.hypothesis import pick_hypothesis
    from aegis.optimizer.state import consumed_hypothesis_ids, rejected_ids

    _patch_optimizer_home(monkeypatch, tmp_path)
    rows = [
        {
            "id": "exp_1",
            "hypothesis_id": "widen_tp_probe",
            "decision": "accept",
            "status": "accepted",
        },
        {
            "id": "exp_2",
            "hypothesis_id": "kaufman_er_gate",
            "decision": "reject",
            "status": "rejected",
        },
    ]
    (tmp_path / "experiments.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows),
        encoding="utf-8",
    )
    (tmp_path / "rejected_experiments.jsonl").write_text(
        json.dumps(rows[1]) + "\n",
        encoding="utf-8",
    )
    assert "widen_tp_probe" not in rejected_ids()
    used = consumed_hypothesis_ids()
    assert "widen_tp_probe" in used
    assert "kaufman_er_gate" in used
    hypo = pick_hypothesis(
        {"metrics": {"win_rate": 35.0, "expectancy_r": -0.03}, "spread_skips": 0},
        {
            "firehose_tp_pips": 2,
            "max_positions": 3,
            "max_spread_pips": 0.8,
            "symbols": ["GBPUSD", "EURAUD", "GBPNZD"],
            "firehose_min_er": 0.0,
            "max_hold_seconds": 0,
        },
        used,
    )
    assert hypo is not None
    assert hypo["id"] == "drop_gbpnzd_spread"


def test_pick_hypothesis_keeps_queue_after_classic_ids_consumed():
    from aegis.optimizer.hypothesis import pick_hypothesis

    used = {
        "scratch_losers_on",
        "cut_max_positions",
        "tighten_spread_gate",
        "widen_tp_probe",
        "kaufman_er_gate",
        "widen_tp_tharp",
        "drop_gbpnzd_spread",
        "tighten_sl_tharp",
        "book_filter_impulse",
        "skip_doji_volman",
        "drop_eurusd_neg_e",
    }
    hypo = pick_hypothesis(
        {"metrics": {"win_rate": 93.0, "expectancy_r": 0.03}, "spread_skips": 2},
        {
            "firehose_tp_pips": 3,
            "firehose_sl_pips": 25,
            "max_positions": 40,
            "max_spread_pips": 0.8,
            "symbols": ["EURUSD", "GBPUSD", "GBPNZD"],
            "firehose_min_er": 0.0,
            "firehose_require_body": False,
            "firehose_min_range_pips": 0.0,
            "max_hold_seconds": 0,
        },
        used,
    )
    assert hypo is not None
    assert hypo["id"] == "require_body_volman"
    assert hypo["patch"] == {"firehose_require_body": True}


def test_pick_hypothesis_fat_spread_before_tp_widen():
    from aegis.optimizer.hypothesis import pick_hypothesis

    used = {
        "scratch_losers_on",
        "cut_max_positions",
        "tighten_spread_gate",
        "widen_tp_probe",
        "kaufman_er_gate",
        "widen_tp_tharp",
        "drop_gbpnzd_spread",
        "tighten_sl_tharp",
        "book_filter_impulse",
        "skip_doji_volman",
        "drop_eurusd_neg_e",
        "require_body_volman",
        "min_range_one_pip",
    }
    hypo = pick_hypothesis(
        {"metrics": {"win_rate": 93.0, "expectancy_r": 0.03}, "spread_skips": 2},
        {
            "firehose_tp_pips": 3,
            "firehose_sl_pips": 25,
            "max_positions": 40,
            "max_spread_pips": 0.8,
            "symbols": ["EURUSD", "GBPUSD", "GBPNZD", "EURJPY"],
            "firehose_min_er": 0.0,
            "firehose_require_body": True,
            "firehose_min_range_pips": 1.0,
            "session_start_utc": 0,
            "session_end_utc": 24,
            "max_hold_seconds": 0,
        },
        used,
    )
    assert hypo is not None
    assert hypo["id"] == "drop_fat_nzd_crosses"
    assert "GBPNZD" not in hypo["patch"]["symbols"]
    assert hypo["patch"].get("session_start_utc") is None
    used.add("drop_fat_nzd_crosses")
    nxt = pick_hypothesis(
        {"metrics": {"win_rate": 93.0, "expectancy_r": 0.03}, "spread_skips": 2},
        {
            "firehose_tp_pips": 3,
            "firehose_sl_pips": 25,
            "max_positions": 40,
            "max_spread_pips": 0.8,
            "symbols": ["EURUSD", "GBPUSD", "GBPNZD", "EURJPY"],
            "firehose_min_er": 0.0,
            "firehose_require_body": True,
            "firehose_min_range_pips": 1.0,
            "max_hold_seconds": 0,
        },
        used,
    )
    assert nxt is not None
    assert nxt["id"] == "tighten_tp_to_2"
    assert nxt["patch"] == {"firehose_tp_pips": 2}


def test_pick_hypothesis_core_1_30_skips_tp_sl_and_queues_intel():
    from aegis.optimizer.hypothesis import core_live_frozen_keys, pick_hypothesis

    used = {
        "scratch_losers_on",
        "cut_max_positions",
        "tighten_spread_gate",
        "widen_tp_probe",
        "kaufman_er_gate",
        "widen_tp_tharp",
        "drop_gbpnzd_spread",
        "tighten_sl_tharp",
        "book_filter_impulse",
        "skip_doji_volman",
        "drop_eurusd_neg_e",
        "require_body_volman",
        "min_range_one_pip",
        "drop_fat_nzd_crosses",
        "cost_buffer_harris",
        "min_range_half_pip",
        "cost_buffer_mild",
        "kaufman_er_mild",
        "widen_tp_to_5",
        "tighten_spread_mild",
        "drop_eurusd_hunt_e",
        "lock_small_wins_tharp",
        "jpy_cluster_two_clenow",
        "time_stop_30m_tharp",
        "vpa_coulling_filter",
        "brooks_range_fade",
        "damir_structure_gate",
        "nison_chart_read",
        "jansen_factor_score",
        "harris_jump_censor",
        "donadio_oms_pretrade",
        "no_stack_into_red",
        "giveback_lock_tharp",
        "time_stop_5m_volman",
        "intel_rsi_ext_elder",
    }
    cfg = {
        "firehose_tp_pips": 1,
        "firehose_sl_pips": 30,
        "max_positions": 40,
        "max_spread_pips": 0.3,
        "symbols": ["EURUSD", "GBPUSD"],
        "firehose_min_er": 0.0,
        "firehose_require_body": True,
        "firehose_min_range_pips": 1.0,
        "session_start_utc": 0,
        "session_end_utc": 24,
        "max_hold_seconds": 0,
        "flatten_if_profit_usd": 0.05,
        "firehose_jpy_cluster_max": 2,
        "firehose_vpa_filter": True,
        "firehose_brooks_range": True,
        "firehose_damir_structure": True,
        "firehose_chart_read": True,
        "firehose_jansen_filter": True,
        "jansen_score_min": 0.15,
        "firehose_harris_jump": True,
        "oms_pretrade": True,
        "firehose_no_stack_if_red": True,
        "close_if_gave_back": True,
        "intel_enabled": True,
        "intel_skip_rsi_ext": True,
        "cost_buffer": 0.05,
    }
    frozen = core_live_frozen_keys(cfg)
    assert frozen == {"firehose_tp_pips", "firehose_sl_pips"}
    hypo = pick_hypothesis(
        {"metrics": {"win_rate": 93.0, "expectancy_r": -0.02}, "spread_skips": 2},
        cfg,
        used,
        blocked_keys=frozen,
    )
    assert hypo is not None
    assert hypo["id"] == "intel_ema_streak_12"
    assert hypo["patch"].get("intel_max_ema_streak") == 12
    assert "firehose_tp_pips" not in (hypo.get("patch") or {})
    assert "firehose_sl_pips" not in (hypo.get("patch") or {})


def test_promote_preserves_core_tp_sl_and_demo_dd_off(tmp_path: Path, monkeypatch):
    from aegis.optimizer.promote import promote_if_flat

    _patch_optimizer_home(monkeypatch, tmp_path)
    accepted = tmp_path / "accepted.yaml"
    live = tmp_path / "live.yaml"
    dump_config(
        {
            "symbol": "GBPUSD",
            "timeframe": "1m",
            "mode": "mt5_demo",
            "firehose_tp_pips": 3,
            "firehose_sl_pips": 25,
            "max_total_drawdown_percent": 12.0,
            "intel_enabled": True,
            "intel_skip_rsi_ext": True,
        },
        accepted,
    )
    dump_config(
        {
            "symbol": "GBPUSD",
            "timeframe": "1m",
            "mode": "mt5_demo",
            "firehose_tp_pips": 1,
            "firehose_sl_pips": 30,
            "firehose_every_bar": True,
            "session_start_utc": 0,
            "session_end_utc": 24,
            "order_quantity": 0.01,
            "max_positions": 40,
            "allow_live": False,
            "max_daily_loss_percent": 0,
            "max_total_drawdown_percent": 0,
        },
        live,
    )
    monkeypatch.setattr(
        "aegis.optimizer.promote.load_heartbeat",
        lambda path=None: {"open": 0, "pid": 1},
    )
    result = promote_if_flat(live_config=live, accepted=accepted, restart=False)
    assert result["promoted"] is True
    got = load_config(live)
    assert float(got["firehose_tp_pips"]) == 1.0
    assert float(got["firehose_sl_pips"]) == 30.0
    assert float(got["max_total_drawdown_percent"]) == 0.0
    assert got.get("intel_enabled") is True
    assert got.get("intel_skip_rsi_ext") is True


def test_pending_frozen_keys_block_another_tp_widen():
    from aegis.optimizer.hypothesis import pending_frozen_keys, pick_hypothesis

    frozen = pending_frozen_keys(
        {"firehose_tp_pips": 1, "symbols": ["GBPUSD", "GBPNZD"]},
        {"firehose_tp_pips": 3, "symbols": ["GBPUSD", "GBPNZD"]},
    )
    assert frozen == {"firehose_tp_pips"}
    hypo = pick_hypothesis(
        {"metrics": {"win_rate": 91.0, "expectancy_r": -0.01}, "spread_skips": 0},
        {
            "firehose_tp_pips": 3,
            "max_positions": 3,
            "max_spread_pips": 0.8,
            "symbols": ["GBPUSD", "EURAUD", "GBPNZD"],
            "firehose_min_er": 0.0,
            "max_hold_seconds": 0,
        },
        rejected=set(),
        blocked_keys=frozen,
    )
    assert hypo is not None
    assert hypo["id"] == "kaufman_er_gate"
    assert "firehose_tp_pips" not in (hypo.get("patch") or {})
    sl_frozen = pending_frozen_keys(
        {"firehose_tp_pips": 1, "firehose_sl_pips": 30},
        {"firehose_tp_pips": 3, "firehose_sl_pips": 25},
    )
    assert sl_frozen == {"firehose_tp_pips", "firehose_sl_pips"}


def test_knowledge_maps_tharp_without_dumping_library():
    from aegis.optimizer.knowledge import WEAKNESS_MAP, lookup_concept

    hit = lookup_concept("high_wr_neg_e")
    assert "CORE_TWELVE" in hit["book_file"]
    assert hit["concept"] == "tharp_expectancy"
    assert set(WEAKNESS_MAP) == {
        "spread_bleed",
        "chop",
        "high_wr_neg_e",
        "impulse_censor",
        "correlation_cluster",
        "session_clock",
    }


def test_cursor_proposal_extracts_yaml_only_and_blocks_live_flags():
    from aegis.optimizer.cursor_cli import extract_proposal, extract_proposal_from_cli

    ok = extract_proposal('noise {"id": "widen_tp", "patch": {"firehose_tp_pips": 2}, "weakness": "high_wr_neg_e", "rationale": "Tharp"}')
    assert ok is not None
    assert ok["patch"] == {"firehose_tp_pips": 2}
    assert extract_proposal('{"id": "x", "patch": {"allow_live": true}}') is None
    assert extract_proposal('{"id": "x", "patch": {"not_a_key": 1}}') is None
    assert extract_proposal('{"id": "x", "patch": {"firehose_every_bar": false}}') is None
    assert extract_proposal('{"id": "x", "patch": {"session_start_utc": 12, "session_end_utc": 17}}') is None
    wrapped = extract_proposal_from_cli(
        '{"type":"result","result":"{\\"id\\":\\"widen_tp\\",\\"patch\\":{\\"firehose_tp_pips\\":2},\\"weakness\\":\\"high_wr_neg_e\\",\\"rationale\\":\\"Tharp\\"}"}',
        "",
    )
    assert wrapped is not None
    assert wrapped["patch"]["firehose_tp_pips"] == 2


def test_promote_refuses_active_firehose_yaml(tmp_path: Path, monkeypatch):
    from aegis.optimizer.promote import promote_if_flat

    _patch_optimizer_home(monkeypatch, tmp_path)
    accepted = tmp_path / "accepted.yaml"
    live = tmp_path / "config_mt5_demo_firehose_hw.yaml"
    dump_config({"symbol": "EURUSD", "allow_live": False, "timeframe": "1m", "mode": "mt5_demo"}, accepted)
    dump_config(
        {
            "symbol": "EURUSD",
            "timeframe": "1m",
            "mode": "mt5_demo",
            "firehose_tp_pips": 1,
            "allow_live": False,
        },
        live,
    )
    monkeypatch.setattr(
        "aegis.optimizer.promote.load_heartbeat",
        lambda path=None: {"open": 0, "pid": 1},
    )
    result = promote_if_flat(live_config=live, accepted=accepted, restart=False)
    assert result["promoted"] is False
    assert "firehose" in result["message"].lower()
    assert float(load_config(live)["firehose_tp_pips"]) == 1.0
