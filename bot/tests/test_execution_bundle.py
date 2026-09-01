from __future__ import annotations

import json
from pathlib import Path
import subprocess
from threading import Event, Thread

import pytest

from aegis.intel.execution_bundle import ExecutionBundleLoader, ExecutionContext
from aegis.intel.firehose_brain import IntelligentFirehoseBrain
from aegis.research.external_dag.bundles import ExecutionBundle
from aegis.research.external_dag.catalog import REQUIRED_EXTERNAL_TOOLS
from aegis.research.external_dag.contracts import content_hash
from aegis.research.watcher_algorithms import ALGORITHM_MODULES


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _book_context() -> dict[str, object]:
    return {
        "status": "AVAILABLE",
        "algorithm_count": len(ALGORITHM_MODULES),
        "algorithm_ids": list(ALGORITHM_MODULES),
        "state_hash": SHA_B,
        "artifact_hash": SHA_A,
        "book_registry_hash": content_hash(tuple(ALGORITHM_MODULES)),
        "supporting_algorithms": [ALGORITHM_MODULES[0]],
        "opposing_algorithms": [],
        "missing_data_algorithms": list(ALGORITHM_MODULES[1:]),
        "supporting_count": 1,
        "opposing_count": 0,
        "missing_data_count": len(ALGORITHM_MODULES) - 1,
        "absolute_views": True,
        "compiled_from_artifact": True,
        "execution_authority": False,
        "research_only": True,
        "no_lookahead": True,
        "order_intent": False,
    }


def _research_provenance() -> dict[str, object]:
    tool_ids = sorted(REQUIRED_EXTERNAL_TOOLS) + ["aegis-book-algorithms"]
    return {
        "book_registry_hash": content_hash(tuple(ALGORITHM_MODULES)),
        "nodes": [
            {
                "node_id": f"node-{index}",
                "tool_id": tool_id,
                "status": "SUCCESS",
                "request_id": f"request-{index}",
                "artifact_hashes": [SHA_A],
                "execution_authority": False,
            }
            for index, tool_id in enumerate(tool_ids)
        ],
    }


def _bundle(
    *,
    expires_at: float = 4_100_000_000.0,
    probability: float = 0.63,
    book_context: dict | None = None,
) -> ExecutionBundle:
    return ExecutionBundle(
        research_bundle_hash=SHA_A,
        dataset_hash=SHA_A,
        validation_hash=SHA_B,
        model_artifact_hash=SHA_C,
        target_definition="captured_exit_replay",
        authorized_symbols=("EURUSD",),
        authorized_horizons_s=(3,),
        models={
            "EURUSD": {
                "BUY": {"micro_momentum": {"3": {
                    "p_captured_win": probability,
                    "threshold": 0.55,
                    "decision": True,
                    "expected_net_pnl": 0.02,
                    "expected_net_pnl_lcb95": 0.005,
                    "calibration_status": "CALIBRATED",
                    "evidence_n": 80,
                    "evidence_losses": 18,
                }}}
            }
        },
        validation={
            "chronological_test": {
                "expectancy": 0.01,
                "profit_factor": 1.2,
                "n_trades": 80,
                "n_losses": 18,
            },
            "validation_oos": {
                "expectancy": 0.008,
                "profit_factor": 1.1,
                "n_trades": 40,
                "n_losses": 8,
            },
            "sealed_oos": {
                "expectancy": 0.01,
                "profit_factor": 1.15,
                "n_trades": 45,
                "n_losses": 9,
            },
            "research_provenance": _research_provenance(),
        },
        book_context=book_context or _book_context(),
        book_algorithm_count=len(ALGORITHM_MODULES),
        created_at=1_700_000_000.0,
        expires_at=expires_at,
    )


def _write(path: Path, bundle: ExecutionBundle) -> None:
    path.write_text(json.dumps(bundle.as_dict()), encoding="utf-8")


def test_loader_loads_once_and_unchanged_hash_does_no_work(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    _write(path, _bundle())
    context = ExecutionContext()
    loader = ExecutionBundleLoader(path, context=context, clock=lambda: 2_000_000_000.0)

    first = loader.refresh_if_changed()
    second = loader.refresh_if_changed()

    assert first.status == "LOADED"
    assert second.status == "UNCHANGED"
    assert context.model_for("EURUSD", "BUY", "micro_momentum", 3)["p_captured_win"] == pytest.approx(0.63)
    assert context.model_for("GBPUSD", "BUY", "micro_momentum", 3) is None


def test_partial_or_mutated_write_keeps_last_known_good_snapshot(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    original = _bundle()
    _write(path, original)
    context = ExecutionContext()
    loader = ExecutionBundleLoader(path, context=context, clock=lambda: 2_000_000_000.0)
    assert loader.refresh_if_changed().status == "LOADED"

    path.write_text('{"schema_version":', encoding="utf-8")
    partial = loader.refresh_if_changed()
    assert partial.status == "IGNORED_INVALID"
    assert context.snapshot().bundle_hash == original.bundle_hash

    mutated = original.as_dict()
    mutated["models"]["EURUSD"]["BUY"]["micro_momentum"]["3"]["p_captured_win"] = 0.99
    path.write_text(json.dumps(mutated), encoding="utf-8")
    invalid = loader.refresh_if_changed()
    assert invalid.status == "IGNORED_INVALID"
    assert "hash mismatch" in invalid.reason
    assert context.model_for("EURUSD", "BUY", "micro_momentum", 3)["p_captured_win"] == pytest.approx(0.63)


def test_expired_bundle_is_not_installed(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    _write(path, _bundle(expires_at=1_900_000_000.0))
    context = ExecutionContext()
    result = ExecutionBundleLoader(
        path, context=context, clock=lambda: 2_000_000_000.0
    ).refresh_if_changed()

    assert result.status == "IGNORED_EXPIRED"
    assert context.snapshot() is None


def test_concurrent_readers_see_only_complete_old_or_new_snapshots(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    old = _bundle(probability=0.61)
    new = _bundle(probability=0.72)
    _write(path, old)
    context = ExecutionContext()
    loader = ExecutionBundleLoader(path, context=context, clock=lambda: 2_000_000_000.0)
    loader.refresh_if_changed()
    stop = Event()
    observed: set[float] = set()

    def reader() -> None:
        while not stop.is_set():
            model = context.model_for("EURUSD", "BUY", "micro_momentum", 3)
            if model is not None:
                observed.add(float(model["p_captured_win"]))

    thread = Thread(target=reader)
    thread.start()
    try:
        _write(path, new)
        assert loader.refresh_if_changed().status == "LOADED"
    finally:
        stop.set()
        thread.join(timeout=2.0)
    assert observed <= {0.61, 0.72}
    assert context.model_for("EURUSD", "BUY", "micro_momentum", 3)["p_captured_win"] == pytest.approx(0.72)


def test_in_memory_hot_path_never_spawns_or_discovers_files(monkeypatch):
    context = ExecutionContext()
    context.install(_bundle(), loaded_at=2_000_000_000.0)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned")))
    monkeypatch.setattr(Path, "glob", lambda *a, **k: (_ for _ in ()).throw(AssertionError("globbed")))

    metadata = context.runtime_metadata("EURUSD", "BUY", "micro_momentum", 3)
    assert metadata["execution_bundle_hash"] == context.snapshot().bundle_hash
    assert metadata["research_bundle_hash"] == SHA_A
    assert metadata["dataset_hash"] == SHA_A
    assert metadata["validation_hash"] == SHA_B
    assert metadata["model_artifact_hash"] == SHA_C
    assert metadata["target_definition"] == "captured_exit_replay"
    assert metadata["book_algorithm_count"] == len(ALGORITHM_MODULES)
    assert metadata["book_context"]["compiled_from_artifact"] is True
    assert metadata["research_provenance"]["book_registry_hash"] == content_hash(tuple(ALGORITHM_MODULES))
    assert metadata["p_captured_win"] == pytest.approx(0.63)


def test_brain_reads_exact_candidate_bundle_only_from_memory(monkeypatch):
    context = ExecutionContext()
    context.install(_bundle(), loaded_at=2_000_000_000.0)
    brain = IntelligentFirehoseBrain.__new__(IntelligentFirehoseBrain)
    brain.execution_context = context
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned")))
    monkeypatch.setattr(Path, "glob", lambda *a, **k: (_ for _ in ()).throw(AssertionError("globbed")))

    prediction = brain.execution_bundle_prediction(
        symbol="EURUSD", side="buy", mechanism="micro_momentum", horizon_s=3
    )
    assert prediction["probability"] == pytest.approx(0.63)
    assert prediction["source"] == "validated_execution_bundle"
    assert brain.execution_bundle_prediction(
        symbol="EURUSD", side="sell", mechanism="micro_momentum", horizon_s=3
    ) is None


def test_brain_prediction_keeps_model_authority_and_attaches_book_fusion():
    context = ExecutionContext()
    book = _book_context()
    book["supporting_algorithms"] = list(ALGORITHM_MODULES[:8])
    book["opposing_algorithms"] = list(ALGORITHM_MODULES[8:10])
    book["missing_data_algorithms"] = list(ALGORITHM_MODULES[10:])
    book.update({
        "supporting_count": 8,
        "opposing_count": 2,
        "missing_data_count": len(ALGORITHM_MODULES) - 10,
    })
    context.install(
        _bundle(book_context=book),
        loaded_at=2_000_000_000.0,
    )
    brain = IntelligentFirehoseBrain.__new__(IntelligentFirehoseBrain)
    brain.execution_context = context

    prediction = brain.execution_bundle_prediction(
        symbol="EURUSD", side="buy", mechanism="micro_momentum", horizon_s=3
    )

    assert prediction["probability"] == pytest.approx(0.63)
    assert prediction["prediction_fusion"]["book_support_score"] == pytest.approx(0.8)
    assert prediction["prediction_fusion"]["decision"] is True
    assert prediction["prediction_fusion"]["execution_authority"] is False


@pytest.mark.parametrize(
    "field",
    ("research_bundle_hash", "dataset_hash", "validation_hash", "model_artifact_hash"),
)
def test_execution_bundle_rejects_non_sha256_identity(field):
    values = _bundle().as_dict()
    values[field] = "not-a-sha256"
    values["bundle_hash"] = ""

    with pytest.raises(ValueError, match=field):
        ExecutionBundle.from_dict(values)


def test_loader_rejects_models_outside_authorized_symbol_scope(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    invalid = _bundle()
    raw = invalid.as_dict()
    raw["models"]["GBPUSD"] = raw["models"]["EURUSD"]
    raw["bundle_hash"] = ""
    # Rebuild the self-consistent envelope; the loader must still reject the
    # model because GBPUSD is not in authorized_symbols.
    _write(path, ExecutionBundle.from_dict(raw))

    context = ExecutionContext()
    result = ExecutionBundleLoader(
        path, context=context, clock=lambda: 2_000_000_000.0
    ).refresh_if_changed()

    assert result.status == "IGNORED_INVALID"
    assert "authorized" in result.reason
    assert context.snapshot() is None


def test_loader_rejects_research_provenance_with_broker_authority(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    raw = _bundle().as_dict()
    raw["validation"]["research_provenance"] = {
        "book_registry_hash": SHA_A,
        "nodes": [{"tool_id": "qlib", "execution_authority": True}],
    }
    raw["bundle_hash"] = ""
    _write(path, ExecutionBundle.from_dict(raw))

    context = ExecutionContext()
    result = ExecutionBundleLoader(
        path, context=context, clock=lambda: 2_000_000_000.0
    ).refresh_if_changed()

    assert result.status == "IGNORED_INVALID"
    assert "authority" in result.reason
    assert context.snapshot() is None


def test_loader_rejects_incomplete_research_provenance(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    raw = _bundle().as_dict()
    raw["validation"]["research_provenance"] = {
        "book_registry_hash": SHA_A,
        "nodes": [{
            "tool_id": "qlib",
            "status": "FAILED",
            "execution_authority": False,
        }],
    }
    raw["bundle_hash"] = ""
    _write(path, ExecutionBundle.from_dict(raw))

    result = ExecutionBundleLoader(
        path, context=ExecutionContext(), clock=lambda: 2_000_000_000.0
    ).refresh_if_changed()

    assert result.status == "IGNORED_INVALID"
    assert "not successful" in result.reason


def test_loader_rejects_book_context_with_execution_authority(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    raw = _bundle().as_dict()
    raw["book_context"] = {
        "status": "AVAILABLE",
        "execution_authority": True,
        "research_only": False,
        "no_lookahead": True,
    }
    raw["bundle_hash"] = ""
    _write(path, ExecutionBundle.from_dict(raw))

    result = ExecutionBundleLoader(
        path, context=ExecutionContext(), clock=lambda: 2_000_000_000.0
    ).refresh_if_changed()

    assert result.status == "IGNORED_INVALID"
    assert "book context" in result.reason


def test_loader_rejects_top_level_book_algorithm_count_mismatch(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    raw = _bundle().as_dict()
    raw["book_algorithm_count"] = len(ALGORITHM_MODULES) - 1
    raw["bundle_hash"] = ""
    _write(path, ExecutionBundle.from_dict(raw))

    result = ExecutionBundleLoader(
        path, context=ExecutionContext(), clock=lambda: 2_000_000_000.0
    ).refresh_if_changed()

    assert result.status == "IGNORED_INVALID"
    assert "book algorithm coverage" in result.reason


def test_loader_rejects_bundle_without_github_book_provenance(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    raw = _bundle().as_dict()
    raw["validation"].pop("research_provenance", None)
    raw["bundle_hash"] = ""
    _write(path, ExecutionBundle.from_dict(raw))

    result = ExecutionBundleLoader(
        path, context=ExecutionContext(), clock=lambda: 2_000_000_000.0
    ).refresh_if_changed()

    assert result.status == "IGNORED_INVALID"
    assert "research provenance" in result.reason


def test_loader_rejects_bundle_with_non_positive_validation_oos(tmp_path: Path):
    path = tmp_path / "execution_bundle.json"
    raw = _bundle().as_dict()
    raw["validation"]["validation_oos"]["expectancy"] = -0.01
    raw["bundle_hash"] = ""
    _write(path, ExecutionBundle.from_dict(raw))

    result = ExecutionBundleLoader(
        path, context=ExecutionContext(), clock=lambda: 2_000_000_000.0
    ).refresh_if_changed()

    assert result.status == "IGNORED_INVALID"
    assert "validation" in result.reason
