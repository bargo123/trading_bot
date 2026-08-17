from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.research.dataset import FORBIDDEN_FEATURE_KEYS, LookaheadError, clips_from_journal
from aegis.research.gates import GateReject, evaluate_promotion
from aegis.research.train import train_pnl_filter


def _write_journal(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_clips_pair_fifo_and_keep_entry_features_only(tmp_path: Path):
    journal = tmp_path / "j.jsonl"
    _write_journal(
        journal,
        [
            {
                "event": "order",
                "ok": True,
                "symbol": "EURUSD",
                "side": "buy",
                "qty": 0.01,
                "spread": 0.00002,
                "bar": "2026-08-13 01:00:00+00:00",
                "intel_quality": 0.4,
                "quote_age_s": 0.2,
                "t2t_ms": 12.0,
                "reason": "firehose_bar_up",
                "sl": 1.09,
                "tp": 1.101,
            },
            {
                "event": "flatten",
                "ok": True,
                "symbol": "EURUSD",
                "pnl": -0.11,
                "held_s": 90.0,
                "equity": 80.0,
                "reason": "tp_sl",
            },
            {
                "event": "order",
                "ok": True,
                "symbol": "GBPUSD",
                "side": "sell",
                "qty": 0.01,
                "spread": 0.00003,
                "bar": "2026-08-13 02:00:00+00:00",
                "reason": "firehose_bar_dn",
                "sl": 1.36,
                "tp": 1.329,
            },
            {
                "event": "flatten",
                "ok": True,
                "symbol": "GBPUSD",
                "pnl": 0.05,
                "held_s": 40.0,
                "equity": 80.05,
            },
        ],
    )
    clips = clips_from_journal(journal)
    assert len(clips) == 2
    assert clips[0]["pnl"] == pytest.approx(-0.11)
    assert clips[0]["symbol"] == "EURUSD"
    assert clips[0]["side"] == "buy"
    for key in FORBIDDEN_FEATURE_KEYS:
        assert key not in clips[0]["features"]
    assert "spread" in clips[0]["features"]
    assert "held_s" not in clips[0]["features"]
    assert "equity" not in clips[0]["features"]


def test_feature_matrix_rejects_label_leak():
    from aegis.research.dataset import assert_no_lookahead

    with pytest.raises(LookaheadError, match="lookahead"):
        assert_no_lookahead({"pnl": 1.0, "spread": 0.0001})


def test_train_uses_time_holdout_and_does_not_promote_on_win_rate(tmp_path: Path):
    journal = tmp_path / "j.jsonl"
    rows: list[dict] = []
    for i in range(40):
        pnl = 0.05 if i % 3 else -0.12
        bar = f"2026-08-13 {i:02d}:00:00+00:00" if i < 24 else f"2026-08-14 {i - 24:02d}:00:00+00:00"
        rows.append(
            {
                "event": "order",
                "ok": True,
                "symbol": "EURUSD" if i % 2 == 0 else "GBPUSD",
                "side": "buy" if i % 2 == 0 else "sell",
                "qty": 0.01,
                "spread": 0.00002 + (i % 5) * 1e-6,
                "bar": bar,
                "reason": "firehose_bar_up" if i % 2 == 0 else "firehose_bar_dn",
                "sl": 1.10,
                "tp": 1.101,
            }
        )
        rows.append(
            {
                "event": "flatten",
                "ok": True,
                "symbol": "EURUSD" if i % 2 == 0 else "GBPUSD",
                "pnl": pnl,
                "held_s": 60.0,
                "equity": 90.0,
            }
        )
    _write_journal(journal, rows)
    result = train_pnl_filter(journal, holdout_frac=0.3, ridge=1.0)
    assert result["label"] == "research_proxy"
    assert result["not_jansen_ml"] is True
    assert result["win_rate_is_not_the_objective"] is True
    train_end = result["train_bar_max"]
    hold_start = result["holdout_bar_min"]
    assert train_end < hold_start
    with pytest.raises(GateReject, match="expectancy|profit_factor"):
        evaluate_promotion(
            {
                "expectancy": -0.01,
                "profit_factor": 0.5,
                "n_trades": 40,
                "net_pnl": -0.4,
                "win_rate": 1.0,
            },
            champion=None,
        )
    assert result["promoted_live_yaml"] is False
    assert "holdout_expectancy" in result


def test_empty_selection_never_wins_the_ranking():
    from aegis.research.train import rank_trials

    took_nothing = {"n_taken": 0, "expectancy": 0.0, "profit_factor": 0.0}
    real_but_losing = {"n_taken": 30, "expectancy": -0.01, "profit_factor": 0.9}
    ranked, qualifying = rank_trials([took_nothing, real_but_losing], min_trades=20)
    assert qualifying is True
    assert ranked[0] is real_but_losing

    thin = {"n_taken": 3, "expectancy": 0.5, "profit_factor": 3.0}
    ranked, qualifying = rank_trials([took_nothing, thin], min_trades=20)
    assert qualifying is False
    assert ranked[0]["n_taken"] == 3


def test_sweep_winner_ignores_payoffs_whose_tail_was_not_sampled():
    from aegis.research.train import pick_sweep_winner

    lucky = {"tp": 1.0, "sl": 30.0, "holdout_n_losses": 2, "holdout_expectancy": 0.5}
    judgeable = {"tp": 8.0, "sl": 8.0, "holdout_n_losses": 9, "holdout_expectancy": -0.001}
    better = {"tp": 4.0, "sl": 8.0, "holdout_n_losses": 6, "holdout_expectancy": 0.002}

    assert pick_sweep_winner([lucky]) is None
    assert pick_sweep_winner([lucky, judgeable]) is judgeable
    assert pick_sweep_winner([lucky, judgeable, better]) is better
    assert pick_sweep_winner([]) is None


def test_search_ranks_by_expectancy_not_win_rate(tmp_path: Path):
    journal = tmp_path / "j.jsonl"
    rows: list[dict] = []
    for i in range(40):
        pnl = 0.05 if i % 3 else -0.12
        bar = f"2026-08-13 {i:02d}:00:00+00:00" if i < 24 else f"2026-08-14 {i - 24:02d}:00:00+00:00"
        rows.append(
            {
                "event": "order",
                "ok": True,
                "symbol": "EURUSD" if i % 2 == 0 else "GBPUSD",
                "side": "buy" if i % 2 == 0 else "sell",
                "qty": 0.01,
                "spread": 0.00002 + (i % 5) * 1e-6,
                "bar": bar,
                "reason": "firehose_bar_up" if i % 2 == 0 else "firehose_bar_dn",
                "sl": 1.10,
                "tp": 1.101,
            }
        )
        rows.append(
            {
                "event": "flatten",
                "ok": True,
                "symbol": "EURUSD" if i % 2 == 0 else "GBPUSD",
                "pnl": pnl,
                "held_s": 60.0,
                "equity": 90.0,
            }
        )
    _write_journal(journal, rows)
    from aegis.research.train import search_pnl_filters

    result = search_pnl_filters(journal, holdout_frac=0.3, round_id="test")
    assert result["rank_metric"] == "holdout_expectancy"
    assert result["win_rate_is_not_the_objective"] is True
    assert result["n_searches"] >= 32
    assert result["promoted_live_yaml"] is False
