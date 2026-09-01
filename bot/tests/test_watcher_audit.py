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


def test_ml_summary_distinguishes_unique_survivors_from_hierarchical_rows(tmp_path):
    report = tmp_path / "ml_pipeline.json"
    report.write_text(
        json.dumps({
            "strategy_selection": {
                "n_shortlisted": 43,
                "n_survive": 1,
                "n_survive_rows": 2,
            },
            "ml": {"improvement_expectancy": 0.5},
        }),
        encoding="utf-8",
    )

    summary = w._summarize_ml(report)

    assert summary["strategies_survive"] == 1
    assert summary["strategy_survivor_rows"] == 2


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


def test_research_watcher_does_not_run_council_without_explicit_opt_in(monkeypatch):
    calls = []
    monkeypatch.setattr(w, "_evidence_changed", lambda: (False, 0))
    monkeypatch.setattr(w, "_notes_changed", lambda: False)
    monkeypatch.setattr(w, "staleness_report", lambda: {"alerts": []})
    monkeypatch.setattr(w, "_evidence_trigger", lambda: "new_closed_trades")
    monkeypatch.setattr(w, "_run_council_round", lambda **kwargs: calls.append(kwargs) or {"ok": True})
    monkeypatch.setattr(w, "_run_script", lambda *args, **kwargs: {"ok": True, "stdout_json": {}})
    monkeypatch.setattr(w, "write_status", lambda **kwargs: "status")
    monkeypatch.setattr(w, "write_heartbeat", lambda **kwargs: "heartbeat")

    result = w.run_cycle(1, fetch_exit=False)

    assert calls == []
    assert result["council"] is None


def test_external_dag_refresh_builds_manifest_then_runs_github_book_workflow(
    monkeypatch, tmp_path
):
    leaderboard = tmp_path / "leaderboard.json"
    shadow_rows = tmp_path / "rows.jsonl"
    selected_replay = tmp_path / "selected_replay.json"
    leaderboard.write_text("{}", encoding="utf-8")
    shadow_rows.write_text("{}\n", encoding="utf-8")
    selected_replay.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "external_manifest.json"
    artifacts = tmp_path / "artifacts"
    status = tmp_path / "status.json"
    registry = tmp_path / "experiments.sqlite"
    bundle = tmp_path / "execution_bundle.json"
    monkeypatch.setattr(w, "FAST_EDGE_LEADERBOARD", leaderboard)
    monkeypatch.setattr(w, "FAST_EDGE_SHADOW_ROWS", shadow_rows)
    monkeypatch.setattr(w, "SELECTED_STRATEGY_REPLAY", selected_replay)
    monkeypatch.setattr(w, "EXTERNAL_DAG_MANIFEST", manifest)
    monkeypatch.setattr(w, "EXTERNAL_DAG_ARTIFACTS", artifacts)
    monkeypatch.setattr(w, "EXTERNAL_DAG_STATUS", status)
    monkeypatch.setattr(w, "EXTERNAL_DAG_REGISTRY", registry)
    monkeypatch.setattr(w, "EXTERNAL_DAG_BUNDLE", bundle)
    calls = []

    def fake_run_script(name, *args, **kwargs):
        calls.append((name, args, kwargs))
        return {
            "ok": True,
            "stdout_json": {"run_id": "fake-run", "promotion_status": "SHADOW_ONLY"},
        }

    monkeypatch.setattr(w, "_run_script", fake_run_script)

    result = w._run_external_dag(7)

    assert result["ok"] is True
    assert result["promotion_status"] == "SHADOW_ONLY"
    assert [call[0] for call in calls] == [
        "build_external_dag_manifest.py",
        "run_external_research_dag.py",
    ]
    manifest_args = calls[0][1]
    assert "--selected-replay" in manifest_args
    assert str(selected_replay) in manifest_args
    dag_args = calls[1][1]
    assert "--dataset-manifest" in dag_args
    assert str(manifest) in dag_args
    assert "--execution-bundle-path" in dag_args
    assert str(bundle) in dag_args
    assert "run_broker_paper.py" not in " ".join(dag_args)


def test_external_dag_refresh_skips_without_frozen_source_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "FAST_EDGE_LEADERBOARD", tmp_path / "missing-leaderboard.json")
    monkeypatch.setattr(w, "FAST_EDGE_SHADOW_ROWS", tmp_path / "missing-rows.jsonl")
    calls = []
    monkeypatch.setattr(w, "_run_script", lambda *args, **kwargs: calls.append(args))

    result = w._run_external_dag(8)

    assert result == {"ok": True, "skipped": "source_inputs_missing"}
    assert calls == []


def test_external_dag_refresh_fails_closed_without_selected_replay(monkeypatch, tmp_path):
    leaderboard = tmp_path / "leaderboard.json"
    shadow_rows = tmp_path / "rows.jsonl"
    leaderboard.write_text("{}", encoding="utf-8")
    shadow_rows.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(w, "FAST_EDGE_LEADERBOARD", leaderboard)
    monkeypatch.setattr(w, "FAST_EDGE_SHADOW_ROWS", shadow_rows)
    monkeypatch.setattr(w, "SELECTED_STRATEGY_REPLAY", tmp_path / "missing-selected.json")

    result = w._run_external_dag(8)

    assert result["ok"] is False
    assert result["stage"] == "selected_replay"
    assert result["reason"] == "selected_strategy_replay_missing"


def test_run_cycle_refreshes_external_dag_after_new_evidence(monkeypatch):
    monkeypatch.setattr(w, "_evidence_changed", lambda: (True, 1))
    monkeypatch.setattr(w, "_notes_changed", lambda: False)
    monkeypatch.setattr(w, "staleness_report", lambda: {"alerts": []})
    monkeypatch.setattr(
        w,
        "_run_script",
        lambda *args, **kwargs: {"ok": True, "stdout_json": {}},
    )
    monkeypatch.setattr(w, "_run_external_dag", lambda tick: {"ok": True, "run_id": f"run-{tick}"})
    monkeypatch.setattr(w, "write_status", lambda **kwargs: "status")
    monkeypatch.setattr(w, "write_heartbeat", lambda **kwargs: "heartbeat")

    result = w.run_cycle(9, fetch_exit=False, ingest_enabled=False)

    assert result["external_dag"] == {"ok": True, "run_id": "run-9"}
