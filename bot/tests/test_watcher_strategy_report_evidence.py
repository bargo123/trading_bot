from __future__ import annotations

import json
from pathlib import Path

from scripts.show_watcher_strategy_report import build_strategy_report, render_strategy_report


def _fixture_report_dir(tmp_path: Path) -> Path:
    report_dir = tmp_path / "watcher"
    report_dir.mkdir()
    rows = []
    for record_id, status in (("exact", "CODED_EXACT"), ("proxy", "FAMILY_PROXY"), ("untestable", "UNTESTABLE_SOURCE")):
        rows.append({
            "record_id": record_id,
            "category": "strategy",
            "source_file": "book_strategy_registry.jsonl",
            "source_line": len(rows) + 1,
            "provenance": {"book": "book-a", "book_hash": "hash-a", "passage_hash": record_id},
            "raw_record": {"strategy_family": "momentum", "side_rule": "BUY", "status": status},
            "validation_status": "UNVALIDATED_RESEARCH",
            "testability": status,
        })
    (report_dir / "knowledge_library.json").write_text(json.dumps({
        "schema": "watcher_knowledge_library.v1",
        "corpus_version": "fixture-v1",
        "counts": {"records": len(rows), "strategy_records": len(rows)},
        "records": rows,
    }), encoding="utf-8")
    (report_dir / "strategy_stats.json").write_text(json.dumps({
        "per_strategy": {
            "exact": {"evidence_status": "CODED_EXACT", "evaluated_decisions": 1, "applicable_decisions": 0},
            "proxy": {"evidence_status": "FAMILY_PROXY", "evaluated_decisions": 1, "applicable_decisions": 0},
            "untestable": {"evidence_status": "UNTESTABLE_SOURCE", "evaluated_decisions": 1, "applicable_decisions": 0},
        }
    }), encoding="utf-8")
    (report_dir / "shadow_trades.jsonl").write_text(json.dumps({
        "record_type": "shadow_trade", "shadow_id": "sh1", "strategy_ids": ["proxy"],
        "shadow_status": "CLOSED", "net_pnl_usd": 0.12,
    }) + "\n", encoding="utf-8")
    (report_dir / "outcomes.jsonl").write_text("", encoding="utf-8")
    return report_dir


def test_report_does_not_show_proxy_as_exact_win_rate(tmp_path):
    report = build_strategy_report(_fixture_report_dir(tmp_path))
    row = next(item for item in report["strategies"] if item["record_id"] == "proxy")
    assert row["exact_win_rate"] is None
    assert row["proxy_win_rate"] == 1.0
    assert row["evidence_status"] == "FAMILY_PROXY"


def test_unobserved_strategy_has_explicit_state_not_blank_percent(tmp_path):
    report = build_strategy_report(_fixture_report_dir(tmp_path))
    row = next(item for item in report["strategies"] if item["record_id"] == "untestable")
    assert row["evidence_status"] == "UNTESTABLE_SOURCE"
    assert row["exact_win_rate"] is None
    rendered = render_strategy_report(report, limit=None)
    assert "UNTESTABLE_SOURCE" in rendered
    assert "FAMILY_PROXY" in rendered
    assert "CODED_EXACT_NO_SAMPLES" in rendered
