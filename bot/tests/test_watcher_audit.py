"""Watcher audit tests: staleness detection, singleton, recovery signals."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.research_fast_watcher as w  # noqa: E402


def test_staleness_detects_fresh_runner(monkeypatch, tmp_path):
    hb = tmp_path / "bot_heartbeat.json"
    hb.write_text(json.dumps({"ts": time.time()}), encoding="utf-8")
    journal = tmp_path / "journal.jsonl"
    journal.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(w, "RUNNER_HEARTBEAT", hb)
    monkeypatch.setattr(w, "FIREHOSE_JOURNAL", journal)
    monkeypatch.setattr(w, "_runner_process_alive", lambda: True)
    report = w.staleness_report()
    assert report["stale"] is False
    assert report["alerts"] == []
    assert report["runner_heartbeat_age_s"] is not None
    assert report["journal_age_s"] is not None


def test_staleness_detects_hung_runner(monkeypatch, tmp_path):
    hb = tmp_path / "bot_heartbeat.json"
    hb.write_text(json.dumps({"ts": time.time() - 900}), encoding="utf-8")
    journal = tmp_path / "journal.jsonl"
    journal.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(w, "RUNNER_HEARTBEAT", hb)
    monkeypatch.setattr(w, "FIREHOSE_JOURNAL", journal)
    monkeypatch.setattr(w, "_runner_process_alive", lambda: True)
    report = w.staleness_report()
    assert report["stale"] is True
    assert any(a.startswith("runner_heartbeat_stale") for a in report["alerts"])


def test_staleness_detects_process_down_and_missing_heartbeat(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "RUNNER_HEARTBEAT", tmp_path / "missing.json")
    monkeypatch.setattr(w, "FIREHOSE_JOURNAL", tmp_path / "missing_journal.jsonl")
    monkeypatch.setattr(w, "_runner_process_alive", lambda: False)
    report = w.staleness_report()
    assert report["stale"] is True
    assert "runner_process_down" in report["alerts"]
    assert "runner_heartbeat_missing" in report["alerts"]
    assert "journal_missing" in report["alerts"]


def test_staleness_detects_stale_journal(monkeypatch, tmp_path):
    hb = tmp_path / "bot_heartbeat.json"
    hb.write_text(json.dumps({"ts": time.time()}), encoding="utf-8")
    old = time.time() - 3600
    journal = tmp_path / "journal.jsonl"
    journal.write_text("x\n", encoding="utf-8")
    import os

    os.utime(journal, (old, old))
    monkeypatch.setattr(w, "RUNNER_HEARTBEAT", hb)
    monkeypatch.setattr(w, "FIREHOSE_JOURNAL", journal)
    monkeypatch.setattr(w, "_runner_process_alive", lambda: True)
    report = w.staleness_report()
    assert report["stale"] is True
    assert any(a.startswith("journal_stale") for a in report["alerts"])


def test_watcher_uses_singleton_lock(tmp_path, monkeypatch):
    """Second watcher instance must be refused by the lock (CYCLE_ALREADY_RUNNING)."""
    lock = w.ProcessLock(tmp_path / "watcher.lock")
    assert lock.try_acquire() is True
    second = w.ProcessLock(tmp_path / "watcher.lock")
    assert second.try_acquire() is False
    lock.release()
    third = w.ProcessLock(tmp_path / "watcher.lock")
    assert third.try_acquire() is True
    third.release()


def test_incremental_ingest_rejects_bad_row_with_symbol_reason():
    from scripts.research_incremental_ingest import ingest_rows

    result = ingest_rows(["invalid"], symbol="EURUSD")

    assert result["status"] == "FAILED"
    assert "mapping" in result["reason"]
