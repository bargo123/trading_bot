from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.research.watcher_algorithms import ALGORITHM_MODULES
from scripts.show_watcher_strategy_report import build_strategy_report, render_strategy_report


def _write_report_fixture(tmp_path: Path) -> Path:
    report_dir = tmp_path / "watcher"
    report_dir.mkdir()
    strategy_rows = [
        {
            "record_id": "s-buy",
            "category": "strategy",
            "source_file": "strategy_hypotheses.jsonl",
            "source_line": 1,
            "provenance": {"book": "book-a", "book_hash": "hash-a"},
            "raw_record": {"strategy_family": "continuation", "side_rule": "buy"},
            "validation_status": "UNVALIDATED_RESEARCH",
            "testability": "TESTABLE",
        },
        {
            "record_id": "s-sell",
            "category": "strategy",
            "source_file": "firehose_hypotheses.jsonl",
            "source_line": 2,
            "provenance": {"book": "book-b", "book_hash": "hash-b"},
            "raw_record": {"strategy_family": "reversal", "side_rule": "sell"},
            "validation_status": "SHADOW_ONLY",
            "testability": "TESTABLE",
        },
    ]
    (report_dir / "knowledge_library.json").write_text(
        json.dumps({
            "schema": "watcher_knowledge_library.v1",
            "corpus_version": "fixture-v1",
            "counts": {"records": 2, "strategy_records": 2},
            "records": strategy_rows,
        }),
        encoding="utf-8",
    )
    (report_dir / "decision_analysis.jsonl").write_text(json.dumps({
        "record_type": "watcher_decision_analysis",
        "analysis_id": "a1",
        "strategy_opinions": [
            {"record_id": "s-buy", "book": "book-a", "opinion": "BUY", "applicability_status": "APPLICABLE", "reasons": []},
            {"record_id": "s-sell", "book": "book-b", "opinion": "NOT_APPLICABLE", "applicability_status": "NOT_APPLICABLE", "reasons": ["side_mismatch"]},
        ],
    }) + "\n", encoding="utf-8")
    (report_dir / "shadow_trades.jsonl").write_text(json.dumps({
        "record_type": "shadow_trade",
        "shadow_id": "sh1",
        "strategy_ids": ["s-buy"],
        "shadow_status": "CLOSED",
        "net_pnl_usd": 0.12,
    }) + "\n", encoding="utf-8")
    (report_dir / "outcomes.jsonl").write_text(json.dumps({
        "record_type": "production_outcome",
        "outcome_id": "o1",
        "broker_confirmed": True,
        "realized_net_usd": -0.04,
        "features": {"strategy_id": "s-buy", "mechanism": "continuation", "symbol": "EURUSD"},
    }) + "\n", encoding="utf-8")
    return report_dir


def test_report_includes_every_strategy_and_separates_shadow_from_broker_truth(tmp_path):
    report = build_strategy_report(_write_report_fixture(tmp_path))

    assert report["total_strategies"] == 2
    assert report["corpus_version"] == "fixture-v1"
    buy = next(row for row in report["strategies"] if row["record_id"] == "s-buy")
    sell = next(row for row in report["strategies"] if row["record_id"] == "s-sell")
    assert buy["applicable_decisions"] == 1
    assert buy["shadow_closed"] == 1
    assert buy["confirmed_outcomes"] == 1
    assert buy["wins"] == 1
    assert buy["losses"] == 1
    assert buy["net_pnl_usd"] == pytest.approx(0.08)
    assert buy["broker_sample_size"] == 1
    assert buy["broker_net_win_rate"] == 0.0
    assert buy["broker_net_win_rate_percent"] == 0.0
    assert sell["status"] == "EVALUATED_NOT_APPLICABLE"
    assert sell["evaluated_decisions"] == 1
    assert report["books"][0]["book"] == "book-a"

    rendered = render_strategy_report(report, limit=None)
    assert "TOTAL_STRATEGIES=2" in rendered
    assert "BOOK / STUDY OUTCOMES" in rendered
    assert "book-a" in rendered
    assert "s-buy" in rendered
    assert "BROKER_CONFIRMED" in rendered
    assert "BROKER_NET_WIN_RATE" in rendered
    assert "0.00%" in rendered


def test_report_handles_missing_runtime_files_without_fabricating_results(tmp_path):
    report_dir = _write_report_fixture(tmp_path)
    (report_dir / "decision_analysis.jsonl").unlink()
    (report_dir / "shadow_trades.jsonl").unlink()
    (report_dir / "outcomes.jsonl").unlink()

    report = build_strategy_report(report_dir)

    assert report["total_strategies"] == 2
    assert all(row["status"] == "NOT_OBSERVED" for row in report["strategies"])
    assert all(row["net_pnl_usd"] is None for row in report["strategies"])
    assert report["algorithm_count"] == len(ALGORITHM_MODULES)
    assert len(report["algorithm_perspectives"]) == len(ALGORITHM_MODULES)
    assert all(row["shadow_win_rate"] is None for row in report["algorithm_perspectives"])


def test_report_includes_algorithm_perspective_shadow_metrics_separately(tmp_path):
    report_dir = _write_report_fixture(tmp_path)
    (report_dir / "strategy_stats.json").write_text(json.dumps({
        "algorithm_perspectives": {
            "trend_structure": {
                "evaluated_decisions": 8,
                "applicable_decisions": 6,
                "shadow_sample_size": 4,
                "shadow_wins": 3,
                "shadow_losses": 1,
                "shadow_win_rate": 0.75,
                "shadow_win_rate_percent": 75.0,
                "shadow_evidence_source": "shadow_replay_price_only",
            },
        },
    }), encoding="utf-8")

    report = build_strategy_report(report_dir)

    assert report["algorithm_count"] == len(ALGORITHM_MODULES)
    algorithm = next(row for row in report["algorithm_perspectives"] if row["perspective_id"] == "trend_structure")
    assert algorithm["perspective_id"] == "trend_structure"
    assert algorithm["shadow_win_rate"] == 0.75
    assert algorithm["shadow_sample_size"] == 4
    assert algorithm["outcome_metric"] == "shadow_win_rate"
    assert algorithm["p_captured_win"] is None
    rendered = render_strategy_report(report, limit=None)
    assert "ALGORITHM PERSPECTIVE OUTCOMES" in rendered
    assert "SHADOW_WIN_RATE" in rendered
    assert "75.00%" in rendered


def test_report_uses_historical_algorithm_replay_when_live_stats_are_empty(tmp_path):
    report_dir = _write_report_fixture(tmp_path)
    replay_dir = report_dir.parent / "research"
    replay_dir.mkdir()
    (replay_dir / "watcher_algorithm_historical_replay.json").write_text(json.dumps({
        "algorithms": {
            "trend_structure": {
                "evaluated": 20,
                "applicable": 8,
                "signal_samples": 4,
                "wins": 3,
                "losses": 1,
                "draws": 0,
                "win_rate": 0.75,
                "expectancy": 0.01,
                "net_pnl": 0.04,
                "p95_loss": -0.02,
                "profit_factor": 2.0,
                "by_horizon": {"5": {"signal_samples": 2, "win_rate": 1.0}},
            },
        },
    }), encoding="utf-8")

    report = build_strategy_report(report_dir)

    algorithm = next(row for row in report["algorithm_perspectives"] if row["perspective_id"] == "trend_structure")
    assert algorithm["evaluated_decisions"] == 20
    assert algorithm["applicable_decisions"] == 8
    assert algorithm["shadow_sample_size"] == 4
    assert algorithm["shadow_win_rate_percent"] == 75.0
    assert algorithm["shadow_evidence_source"] == "historical_quote_replay_net_pnl"
    assert algorithm["shadow_by_horizon"]["5"]["win_rate"] == 1.0
    assert algorithm["p_captured_win"] is None
