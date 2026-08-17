"""Phase 2 research registry: fingerprints, append-only store, duplicate refuse."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from aegis.research.champion import ChampionStore
from aegis.research.fingerprint import config_fingerprint, dataset_fingerprint
from aegis.research.gates import GateReject, evaluate_promotion
from aegis.research.registry import (
    DuplicateExperimentError,
    EquivalentExperimentError,
    ExperimentRegistry,
)


def test_reused_experiment_id_raises_instead_of_sqlite_error(tmp_path: Path):
    reg = ExperimentRegistry(tmp_path / "exp.sqlite")
    row = {
        "id": "exp_fixed",
        "hypothesis": "first",
        "config_fingerprint": "cfg1",
        "dataset_fingerprint": "ds1",
        "status": "rejected",
    }
    reg.record(row)
    with pytest.raises(DuplicateExperimentError, match="already recorded"):
        reg.record({**row, "hypothesis": "second", "new_reason": "different question"})
    assert len(reg.all_rows()) == 1


def test_config_fingerprint_is_stable_under_key_order():
    a = {"tp": 1, "sl": 30, "nested": {"x": 1, "y": 2}}
    b = {"nested": {"y": 2, "x": 1}, "sl": 30, "tp": 1}
    assert config_fingerprint(a) == config_fingerprint(b)
    assert config_fingerprint(a) != config_fingerprint({"tp": 2, "sl": 30})


def test_dataset_fingerprint_changes_when_a_close_changes():
    t = pd.date_range("2026-01-01", periods=3, freq="min", tz="UTC")
    df = pd.DataFrame({"time": t, "open": 1.0, "high": 1.1, "low": 0.9, "close": [1.0, 1.01, 1.02]})
    other = df.copy()
    other.loc[1, "close"] = 1.05
    assert dataset_fingerprint(df) != dataset_fingerprint(other)


def test_registry_insert_never_deletes_rejected(tmp_path: Path):
    db = tmp_path / "exp.sqlite"
    reg = ExperimentRegistry(db)
    row = {
        "id": "exp_a",
        "hypothesis": "skip doji",
        "config_fingerprint": "cfg1",
        "dataset_fingerprint": "ds1",
        "status": "rejected",
        "rejection_reason": "oos_e worse",
        "expectancy": -0.01,
        "win_rate": 0.97,
        "profit_factor": 0.9,
        "n_trades": 100,
    }
    reg.record(row)
    with pytest.raises(EquivalentExperimentError):
        reg.record({**row, "id": "exp_b", "status": "open"})
    assert [r["id"] for r in reg.all_rows()] == ["exp_a"]


def test_registry_allows_retry_with_explicit_new_reason(tmp_path: Path):
    db = tmp_path / "exp.sqlite"
    reg = ExperimentRegistry(db)
    base = {
        "id": "exp_a",
        "hypothesis": "skip doji",
        "config_fingerprint": "cfg1",
        "dataset_fingerprint": "ds1",
        "status": "rejected",
        "rejection_reason": "oos_e worse",
    }
    reg.record(base)
    reg.record({**base, "id": "exp_b", "status": "open", "new_reason": "new 30d dataset"})
    ids = {r["id"] for r in reg.all_rows()}
    assert ids == {"exp_a", "exp_b"}


def _metrics(**over: object) -> dict:
    base = {
        "expectancy": 0.01,
        "profit_factor": 1.2,
        "n_trades": 80,
        "net_pnl": 2.0,
        "win_rate": 0.6,
        "max_drawdown_pct": 5.0,
    }
    base.update(over)
    return base


def test_gates_reject_high_wr_negative_expectancy():
    with pytest.raises(GateReject, match="expectancy"):
        evaluate_promotion(_metrics(expectancy=-0.01, win_rate=0.99), champion=None)


def test_gates_reject_profit_factor_not_above_one():
    with pytest.raises(GateReject, match="profit_factor"):
        evaluate_promotion(_metrics(profit_factor=1.0), champion=None)


def test_gates_require_strict_beat_of_champion_e_and_pnl():
    champ = {"expectancy": 0.01, "net_pnl": 2.0, "id": "champ"}
    with pytest.raises(GateReject, match="champion"):
        evaluate_promotion(_metrics(expectancy=0.01, net_pnl=3.0), champion=champ)
    with pytest.raises(GateReject, match="champion"):
        evaluate_promotion(_metrics(expectancy=0.02, net_pnl=2.0), champion=champ)
    evaluate_promotion(_metrics(expectancy=0.02, net_pnl=2.5), champion=champ)


def test_champion_promote_does_not_write_live_yaml(tmp_path: Path):
    db = tmp_path / "exp.sqlite"
    live = tmp_path / "live.yaml"
    live.write_text("allow_live: false\n", encoding="utf-8")
    store = ChampionStore(db)
    store.promote(
        {
            "id": "exp_win",
            "hypothesis": "edge",
            "config_fingerprint": "c",
            "dataset_fingerprint": "d",
            "status": "accepted",
            **_metrics(expectancy=0.02, net_pnl=3.0),
        }
    )
    assert store.current()["id"] == "exp_win"
    assert live.read_text(encoding="utf-8") == "allow_live: false\n"
