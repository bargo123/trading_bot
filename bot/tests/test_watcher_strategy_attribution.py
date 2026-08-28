from __future__ import annotations

import json

from scripts.watcher_knowledge_engine import STRUCTURED_KB_FILES, WatcherKnowledgeEngine


def _engine(tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    for name in STRUCTURED_KB_FILES:
        (knowledge / name).write_text("", encoding="utf-8")
    (knowledge / "corpus_manifest.json").write_text(json.dumps({"corpus_version": "fixture"}), encoding="utf-8")
    (knowledge / "source_index.json").write_text(json.dumps({"files": []}), encoding="utf-8")
    return WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=tmp_path / "watcher")


def test_close_uses_frozen_strategy_ids_not_post_entry_state(tmp_path):
    engine = _engine(tmp_path)
    engine.process_event({
        "event": "firehose_open",
        "event_id": "open-1",
        "ticket": "T1",
        "symbol": "EURUSD",
        "side": "BUY",
        "mechanism": "x",
        "horizon_s": 3,
        "strategy_ids": ["s1"],
        "entry_state": {"context_hash": "h1"},
    })
    outputs = engine.process_event({
        "event": "confirmed_close_finalization",
        "event_id": "close-1",
        "ticket": "T1",
        "status": "BROKER_CONFIRMED",
        "broker_facts": {"realized_net_usd": 0.2},
        "strategy_ids": ["s2"],
    })
    outcome = next(row for row in outputs if row["record_type"] == "production_outcome")
    assert outcome["features"]["strategy_ids"] == ["s1"]
    assert outcome["features"]["context_hash"] == "h1"
    assert outcome["attribution_status"] == "ATTRIBUTED"


def test_confirmed_close_without_open_correlation_is_unattributed(tmp_path):
    engine = _engine(tmp_path)
    outputs = engine.process_event({
        "event": "confirmed_close_finalization",
        "event_id": "close-1",
        "ticket": "T1",
        "status": "BROKER_CONFIRMED",
        "broker_facts": {"realized_net_usd": -0.1},
        "strategy_ids": ["s2"],
    })
    outcome = next(row for row in outputs if row["record_type"] == "production_outcome")
    assert outcome["attribution_status"] == "UNATTRIBUTED"
    assert "strategy_ids" not in outcome["features"]
