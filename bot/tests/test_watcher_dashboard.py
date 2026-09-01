from __future__ import annotations

import gzip
import json
from pathlib import Path

from scripts.watcher_dashboard import (
    build_blocked_trade_index,
    load_blocked_studies,
    render_dashboard_html,
    study_detail,
    StudyStore,
)
from scripts.watcher_parquet import append_study, flush_pending_to_parquet


def _write_fixture(tmp_path: Path) -> Path:
    report_dir = tmp_path / "watcher"
    report_dir.mkdir()
    study = {
        "record_type": "blocked_strategy_study",
        "study_id": "study-1",
        "blocked_event_id": "event-1",
        "candidate_state": {
            "candidate_id": "stoch_mr:buy:15s",
            "symbol": "GBPUSD",
            "side": "buy",
            "mechanism": "stoch_mr",
            "horizon_s": 15,
            "reason": "TAIL_RISK_FAILURE",
        },
        "strategy_count": 2,
        "strategies": [
            {"record_id": "s-buy", "opinion": "BUY", "p_captured_win": 0.75, "p_captured_win_percent": 75.0, "p_captured_win_sample_size": 4},
            {"record_id": "s-sell", "opinion": "SELL", "p_captured_win": None, "p_captured_win_sample_size": 0},
        ],
    }
    (report_dir / "blocked_strategy_studies.jsonl").write_text(json.dumps(study) + "\n", encoding="utf-8")
    return report_dir


def test_dashboard_indexes_blocked_trades_without_dropping_strategy_data(tmp_path):
    report_dir = _write_fixture(tmp_path)

    studies = load_blocked_studies(report_dir)
    index = build_blocked_trade_index(studies)

    assert len(index) == 1
    assert index[0]["study_id"] == "study-1"
    assert index[0]["symbol"] == "GBPUSD"
    assert index[0]["side"] == "BUY"
    assert index[0]["strategy_count"] == 2
    assert index[0]["opinion_counts"]["BUY"] == 1
    assert index[0]["opinion_counts"]["SELL"] == 1

    detail = study_detail(studies, "study-1")
    assert detail["strategy_count"] == 2
    assert {row["record_id"] for row in detail["strategies"]} == {"s-buy", "s-sell"}
    assert detail["strategies"][0]["p_captured_win_percent"] == 75.0


def test_dashboard_html_has_click_to_expand_strategy_detail_and_is_read_only():
    html = render_dashboard_html()

    assert "Blocked Trade Studies" in html
    assert "All strategies" in html
    assert "P_CAPTURED_WIN" in html
    assert "Candidate ML prediction" in html
    assert "Book-informed perspectives" in html
    assert "Book algorithms" in html
    assert "Shadow win rate" in html
    assert "book_perspectives" in html
    assert "prediction_evidence" in html
    assert "fetch('/api/blocked-trades'" in html
    assert "fetch('/api/blocked-trade/'" in html


def test_dashboard_preserves_expanded_detail_while_auto_refresh_runs():
    html = render_dashboard_html()

    assert "let expandedStudyId = null" in html
    assert "let expandedDetailHtml = null" in html
    assert "expandedStudyId = card.dataset.id" in html
    assert "expandedDetailHtml = expandedDetailLoaded ? detail.innerHTML : null" in html
    assert "restoreExpandedDetail" in html

    source = Path(__file__).parents[1] / "scripts" / "watcher_dashboard.py"
    text = source.read_text(encoding="utf-8")
    for forbidden in ("mt5.order_send", "place_order", "close_ticket", "aegis.engines", "run_broker_paper"):
        assert forbidden not in text


def test_dashboard_store_reuses_unchanged_report_data(tmp_path):
    report_dir = _write_fixture(tmp_path)
    store = StudyStore(report_dir)

    first = store.load()
    second = store.load()

    assert first is second


def test_dashboard_hydrates_latest_algorithm_shadow_metrics(tmp_path):
    report_dir = _write_fixture(tmp_path)
    study_path = report_dir / "blocked_strategy_studies.jsonl"
    study = json.loads(study_path.read_text(encoding="utf-8").splitlines()[0])
    study["book_perspectives"] = [{"perspective_id": "trend_structure", "shadow_win_rate": None}]
    study_path.write_text(json.dumps(study) + "\n", encoding="utf-8")
    (report_dir / "strategy_stats.json").write_text(json.dumps({
        "algorithm_perspectives": {
            "trend_structure": {
                "shadow_win_rate": 0.75,
                "shadow_win_rate_percent": 75.0,
                "shadow_sample_size": 4,
                "shadow_evidence_source": "shadow_replay_price_only",
            },
        },
    }), encoding="utf-8")

    store = StudyStore(report_dir)
    detail = store.hydrate(store.load_detail("study-1"))

    perspective = detail["book_perspectives"][0]
    assert perspective["shadow_win_rate"] == 0.75
    assert perspective["shadow_win_rate_percent"] == 75.0
    assert perspective["shadow_sample_size"] == 4
    assert perspective["shadow_evidence_source"] == "shadow_replay_price_only"


def test_dashboard_hides_partial_strategy_rows_from_active_library(tmp_path):
    report_dir = _write_fixture(tmp_path)
    (report_dir / "knowledge_library.json").write_text(json.dumps({
        "schema": "watcher_knowledge_library.v1",
        "records": [{
            "category": "strategy",
            "record_id": "s-buy",
            "algorithm_status": "WATCHER_EXACT_RULE",
            "raw_record": {
                "status": "CODED_EXACT",
                "algorithm": {"compiled_entry_predicates": {"structure_eq": "breakout"}},
            },
            "provenance": {"book": "book-a"},
        }],
    }), encoding="utf-8")

    store = StudyStore(report_dir)
    detail = store.hydrate(store.load_detail("study-1"))

    assert detail["strategy_count"] == 1
    assert [row["record_id"] for row in detail["strategies"]] == ["s-buy"]


def test_dashboard_hydrates_historical_algorithm_replay_when_live_stats_are_empty(tmp_path):
    report_dir = _write_fixture(tmp_path)
    study_path = report_dir / "blocked_strategy_studies.jsonl"
    study = json.loads(study_path.read_text(encoding="utf-8").splitlines()[0])
    study["book_perspectives"] = [{"perspective_id": "trend_structure", "shadow_win_rate": None}]
    study_path.write_text(json.dumps(study) + "\n", encoding="utf-8")
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
            },
        },
    }), encoding="utf-8")

    store = StudyStore(report_dir)
    detail = store.hydrate(store.load_detail("study-1"))

    perspective = detail["book_perspectives"][0]
    assert perspective["shadow_win_rate"] == 0.75
    assert perspective["shadow_win_rate_percent"] == 75.0
    assert perspective["shadow_sample_size"] == 4
    assert perspective["shadow_evidence_source"] == "historical_quote_replay_net_pnl"


def test_dashboard_index_loader_avoids_loading_strategy_payload_until_expansion(tmp_path):
    report_dir = _write_fixture(tmp_path)
    store = StudyStore(report_dir)

    index_studies = store.load_index()
    assert len(index_studies) == 1
    assert "strategies" not in index_studies[0]
    assert index_studies[0]["strategy_count"] == 2
    assert build_blocked_trade_index(index_studies)[0]["opinion_counts"] == {"BUY": 1, "SELL": 1, "NO_TRADE": 0, "NOT_APPLICABLE": 0}

    detail = store.load_detail("study-1")
    assert {row["record_id"] for row in detail["strategies"]} == {"s-buy", "s-sell"}


def test_dashboard_uses_compact_index_strategy_count_and_opinions_without_payload():
    compact = {
        "record_type": "blocked_strategy_study",
        "study_id": "compact-1",
        "blocked_event_id": "event-compact-1",
        "candidate_state": {"candidate_id": "cand-compact", "symbol": "EURUSD"},
        "strategy_count": 2424,
        "opinion_counts": {"BUY": 12, "SELL": 8, "NO_TRADE": 4, "NOT_APPLICABLE": 2400},
    }

    row = build_blocked_trade_index([compact])[0]

    assert row["strategy_count"] == 2424
    assert row["opinion_counts"] == compact["opinion_counts"]


def test_dashboard_exposes_book_algorithm_count_when_source_records_are_empty():
    study = {
        "record_type": "blocked_strategy_study",
        "study_id": "algorithms-1",
        "candidate_state": {"symbol": "EURUSD"},
        "strategy_count": 0,
        "strategies": [],
        "book_perspectives": [{"perspective_id": f"algorithm-{index}"} for index in range(103)],
    }

    row = build_blocked_trade_index([study])[0]

    assert row["strategy_count"] == 0
    assert row["algorithm_count"] == 103


def test_dashboard_reads_parquet_details_after_live_index_refresh(tmp_path):
    source_dir = _write_fixture(tmp_path)
    report_dir = tmp_path / "parquet_watcher"
    report_dir.mkdir()
    source = json.loads((source_dir / "blocked_strategy_studies.jsonl").read_text(encoding="utf-8").splitlines()[0])
    append_study(report_dir, source)
    flush_pending_to_parquet(report_dir)

    store = StudyStore(report_dir)
    rows = store.load_index()
    detail = store.load_detail(rows[0]["study_id"])

    assert rows[0]["strategy_count"] == 2
    assert {row["record_id"] for row in detail["strategies"]} == {"s-buy", "s-sell"}


def test_dashboard_loads_compressed_archived_studies(tmp_path):
    report_dir = _write_fixture(tmp_path)
    archive_dir = report_dir / "archives"
    archive_dir.mkdir()
    archived = {
        "record_type": "blocked_strategy_study",
        "study_id": "study-archived",
        "strategy_count": 0,
        "strategies": [],
    }
    with gzip.open(archive_dir / "blocked_strategy_studies_20260828.jsonl.gz", "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(archived) + "\n")

    studies = load_blocked_studies(report_dir)

    assert {row["study_id"] for row in studies} == {"study-1", "study-archived"}
