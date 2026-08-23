from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from aegis.research_factory.core import ResearchFactory, ResearchState
from aegis.research_factory.data import (
    DataPipeline,
    DatasetSplit,
    FeatureEngineer,
    FeatureSet,
    create_research_splits,
    discover_csv_sources,
    engineer_features,
)


def _write_bar_csv(path, time: str = "2026-01-01T00:00:00Z") -> None:
    pd.DataFrame(
        {
            "time": [time],
            "open": [1.1],
            "high": [1.2],
            "low": [1.0],
            "close": [1.15],
        }
    ).to_csv(path, index=False)


def test_discovery_uses_snapshot_metadata_and_keeps_timeframes_separate(tmp_path):
    csv = tmp_path / "EURUSD_X_1m_7d.csv"
    _write_bar_csv(csv)
    csv.with_suffix(".json").write_text(
        json.dumps(
            {
                "symbol": "EURUSD",
                "timeframe": "1m",
                "source": "yahoo_snapshot",
                "quality": "proxy_no_bid_ask",
            }
        )
    )

    sources = discover_csv_sources([tmp_path])
    frame = DataPipeline(min_train_size=1).load_sources(sources)

    assert [(s.symbol, s.timeframe) for s in sources] == [("EURUSD", "1m")]
    assert frame.loc[0, "source_kind"] == "yahoo_snapshot"
    assert frame.loc[0, "source_quality"] == "proxy_no_bid_ask"
    assert frame.loc[0, "source_file"] == str(csv)
    assert str(frame.loc[0, "time"].tz) == "UTC"


def test_discovery_is_recursive_and_returns_empty_without_fallback(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    csv = nested / "GBPUSD_X_5m_59d.csv"
    _write_bar_csv(csv)
    empty_root = tmp_path / "empty"
    empty_root.mkdir()

    sources = discover_csv_sources([tmp_path])

    assert [(source.path, source.symbol, source.timeframe) for source in sources] == [
        (csv, "GBPUSD", "5m")
    ]
    assert discover_csv_sources([empty_root]) == []
    assert DataPipeline(min_train_size=1).load_sources([]).empty


def test_load_sources_skips_unreadable_csv_without_generating_rows(tmp_path, caplog):
    csv = tmp_path / "EURUSD_X_1h_90d.csv"
    csv.write_bytes(b"\xff\xfe")

    frame = DataPipeline(min_train_size=1).load_sources(
        discover_csv_sources([tmp_path])
    )

    assert frame.empty
    assert "Failed to load" in caplog.text


def test_load_sources_deduplicates_identical_overlaps_and_aggregates_provenance(
    tmp_path,
):
    first = tmp_path / "EURUSD_A_1m.csv"
    second = tmp_path / "EURUSD_B_1m.csv"
    for path, source, quality in (
        (first, "broker_archive", "broker_native"),
        (second, "journal_clip", "observed"),
    ):
        _write_bar_csv(path)
        path.with_suffix(".json").write_text(
            json.dumps(
                {
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "source": source,
                    "quality": quality,
                }
            )
        )

    frame = DataPipeline(min_train_size=1).load_sources(
        discover_csv_sources([tmp_path])
    )

    assert len(frame) == 1
    assert frame.loc[0, "source_file"] == "|".join(sorted(map(str, (first, second))))
    assert frame.loc[0, "source_kind"] == "broker_archive|journal_clip"
    assert frame.loc[0, "source_quality"] == "broker_native|observed"


def test_load_sources_rejects_conflicting_overlaps(tmp_path):
    first = tmp_path / "EURUSD_A_1m.csv"
    second = tmp_path / "EURUSD_B_1m.csv"
    _write_bar_csv(first)
    _write_bar_csv(second)
    conflicting = pd.read_csv(second)
    conflicting.loc[0, "close"] = 1.16
    conflicting.to_csv(second, index=False)

    with pytest.raises(ValueError, match="Conflicting duplicate.*EURUSD.*1m"):
        DataPipeline(min_train_size=1).load_sources(
            discover_csv_sources([tmp_path])
        )


def test_fingerprint_hashes_row_101_and_is_order_independent():
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=102, freq="min", tz="UTC"),
            "symbol": ["EURUSD"] * 102,
            "close": [float(value) for value in range(102)],
        }
    )
    reordered = frame[["close", "time", "symbol"]].sample(
        frac=1, random_state=17
    )
    changed = frame.copy()
    changed.loc[100, "close"] = 999.0
    pipeline = DataPipeline(min_train_size=1)

    fingerprint = pipeline.compute_dataset_fingerprint(frame)
    assert len(fingerprint) == 64
    assert fingerprint == (
        pipeline.compute_dataset_fingerprint(reordered)
    )
    assert pipeline.compute_dataset_fingerprint(frame) != (
        pipeline.compute_dataset_fingerprint(changed)
    )


def test_fingerprint_canonicalizes_equivalent_float_nan_encodings():
    first_nan = np.array([0x7FF8000000000000], dtype=np.uint64).view(np.float64)
    second_nan = np.array([0x7FF8000000000001], dtype=np.uint64).view(np.float64)
    pipeline = DataPipeline(min_train_size=1)

    assert pipeline.compute_dataset_fingerprint(
        pd.DataFrame({"value": first_nan})
    ) == pipeline.compute_dataset_fingerprint(pd.DataFrame({"value": second_nan}))


def test_empty_fingerprints_include_column_names_and_dtypes():
    pipeline = DataPipeline(min_train_size=1)
    fingerprints = {
        pipeline.compute_dataset_fingerprint(
            pd.DataFrame({"value": pd.Series(dtype="float64")})
        ),
        pipeline.compute_dataset_fingerprint(
            pd.DataFrame({"value": pd.Series(dtype="int64")})
        ),
        pipeline.compute_dataset_fingerprint(
            pd.DataFrame({"other": pd.Series(dtype="float64")})
        ),
    }

    assert len(fingerprints) == 3


def _label_frame(
    symbol: str = "EURUSD",
    price_scale: float = 1.0,
    timeframe: str = "1m",
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3, freq="min", tz="UTC"),
            "open": np.array([100.0, 100.0, 100.0]) * price_scale,
            "high": np.array([101.0, 104.0, 101.0]) * price_scale,
            "low": np.array([99.0, 99.0, 95.0]) * price_scale,
            "close": np.array([100.0, 100.0, 100.0]) * price_scale,
            "volume": [10.0, 20.0, 30.0],
            "symbol": symbol,
            "timeframe": timeframe,
        }
    )


def test_labels_record_first_barrier_and_leave_unmatured_tail_null():
    frame = _label_frame()
    frame["source_file"] = "fixture.csv"
    frame["source_kind"] = "test"
    frame["source_quality"] = "observed"
    feature_set = FeatureEngineer().engineer(
        frame,
        label_horizon=2,
        profit_barrier_pct=0.02,
        loss_barrier_pct=0.02,
    )

    first = feature_set.labels.iloc[0]
    assert first["profit_barrier_first"] == 1
    assert first["mfe"] == 4.0
    assert first["mae"] == 5.0
    assert first["time_to_target"] == 1
    assert feature_set.labels.iloc[1:].isna().all().all()
    assert feature_set.canonical.columns.is_unique
    assert set(feature_set.label_names).isdisjoint(feature_set.feature_names)
    assert feature_set.canonical["profit_barrier_first"].equals(
        feature_set.labels["profit_barrier_first"]
    )
    metadata = [
        "time",
        "source_file",
        "source_kind",
        "source_quality",
        "symbol",
        "timeframe",
    ]
    assert list(feature_set.canonical.columns) == [
        *metadata,
        *feature_set.feature_names,
        *feature_set.label_names,
    ]


def test_same_bar_barrier_collision_is_classified_as_conservative_loss():
    frame = _label_frame()
    frame.loc[1, ["high", "low"]] = [103.0, 97.0]

    labels = FeatureEngineer().engineer(
        frame,
        label_horizon=2,
        profit_barrier_pct=0.02,
        loss_barrier_pct=0.02,
    ).labels

    assert labels.loc[0, "profit_barrier_first"] == 0
    assert labels.loc[0, "time_to_target"] == 1


def test_mfe_and_mae_are_non_negative_excursions():
    no_favorable_excursion = _label_frame("EURUSD")
    no_favorable_excursion.loc[1:, ["open", "high", "low", "close"]] = [
        [98.5, 99.0, 98.0, 98.5],
        [97.5, 98.0, 97.0, 97.5],
    ]
    no_adverse_excursion = _label_frame("GBPUSD")
    no_adverse_excursion.loc[1:, ["open", "high", "low", "close"]] = [
        [101.5, 102.0, 101.0, 101.5],
        [102.5, 103.0, 102.0, 102.5],
    ]
    frame = pd.concat([no_favorable_excursion, no_adverse_excursion])

    labels = FeatureEngineer().engineer(
        frame,
        label_horizon=2,
        profit_barrier_pct=0.02,
        loss_barrier_pct=0.02,
    ).canonical

    assert labels.loc[labels["symbol"] == "EURUSD", "mfe"].iloc[0] == 0.0
    assert labels.loc[labels["symbol"] == "GBPUSD", "mae"].iloc[0] == 0.0


def test_label_barriers_are_required_and_must_be_positive():
    frame = _label_frame()
    engineer = FeatureEngineer()

    with pytest.raises(TypeError, match="profit_barrier_pct"):
        engineer.engineer(frame, label_horizon=2)
    with pytest.raises(TypeError, match="profit_barrier_pct"):
        engineer_features(frame, label_horizon=2)
    for profit_barrier_pct, loss_barrier_pct in (
        (0.0, 0.02),
        (-0.01, 0.02),
        (0.02, 0.0),
        (0.02, -0.01),
    ):
        with pytest.raises(ValueError, match="barrier_pct"):
            engineer.engineer(
                frame,
                label_horizon=2,
                profit_barrier_pct=profit_barrier_pct,
                loss_barrier_pct=loss_barrier_pct,
            )


def test_symbol_groups_do_not_change_each_others_features_or_labels():
    first = _label_frame()
    second = _label_frame("XAUUSD", price_scale=100.0)
    combined = pd.concat([second, first], ignore_index=True)
    kwargs = {
        "label_horizon": 2,
        "profit_barrier_pct": 0.02,
        "loss_barrier_pct": 0.02,
    }

    isolated = FeatureEngineer().engineer(first, **kwargs).canonical
    together = FeatureEngineer().engineer(combined, **kwargs).canonical
    actual = together.loc[together["symbol"] == "EURUSD"].reset_index(drop=True)

    pd.testing.assert_frame_equal(actual, isolated)


def test_timeframe_groups_do_not_change_each_others_features_or_labels():
    first = _label_frame(timeframe="1m")
    second = _label_frame(timeframe="5m", price_scale=100.0)
    kwargs = {
        "label_horizon": 2,
        "profit_barrier_pct": 0.02,
        "loss_barrier_pct": 0.02,
    }

    isolated = FeatureEngineer().engineer(first, **kwargs).canonical
    together = FeatureEngineer().engineer(
        pd.concat([second, first], ignore_index=True), **kwargs
    ).canonical
    actual = together.loc[together["timeframe"] == "1m"].reset_index(drop=True)

    pd.testing.assert_frame_equal(actual, isolated)


def test_public_data_boundaries_reject_boolean_label_horizon():
    label_frame = _label_frame()
    split_frame = _split_frame(100, ["EURUSD"])

    with pytest.raises(ValueError, match="positive integer"):
        FeatureEngineer().engineer(
            label_frame,
            label_horizon=True,
            profit_barrier_pct=0.02,
            loss_barrier_pct=0.02,
        )
    with pytest.raises(ValueError, match="positive integer"):
        engineer_features(
            label_frame,
            label_horizon=True,
            profit_barrier_pct=0.02,
            loss_barrier_pct=0.02,
        )
    with pytest.raises(ValueError, match="positive integer"):
        DataPipeline(min_train_size=1).create_splits(
            split_frame, label_horizon=True
        )
    with pytest.raises(ValueError, match="positive integer"):
        create_research_splits(split_frame, label_horizon=True)


def test_splits_keep_timestamps_together_and_purge_each_series_horizon():
    timestamps = pd.date_range("2026-01-01", periods=100, freq="min", tz="UTC")
    frame = pd.DataFrame(
        {
            "time": timestamps.repeat(2),
            "symbol": ["EURUSD", "XAUUSD"] * 100,
            "timeframe": "1m",
            "profit_barrier_first": 1.0,
            "row_id": np.arange(200),
        }
    )
    unknown_target_row = int(
        frame.index[
            (frame["time"] == timestamps[10]) & (frame["symbol"] == "EURUSD")
        ][0]
    )
    frame.loc[unknown_target_row, "profit_barrier_first"] = np.nan

    split = DataPipeline(min_train_size=1).create_splits(
        frame, label_horizon=3
    )
    parts = (
        split.train,
        split.validation,
        split.test,
        split.sealed_holdout,
    )

    assert split.train.time.max() < split.validation.time.min()
    assert split.validation.time.max() < split.test.time.min()
    assert split.test.time.max() < split.sealed_holdout.time.min()
    for timestamp in frame.time.unique():
        memberships = sum(timestamp in set(part.time) for part in parts)
        assert memberships <= 1
    assert unknown_target_row not in set(
        pd.concat(parts, ignore_index=True)["row_id"]
    )
    assert split.split_info["label_horizon"] == 3
    assert split.split_info["purged_rows"] == 18
    assert split.split_info["timestamp_bounds"]["train"] == {
        "start": timestamps[0].isoformat(),
        "end": timestamps[56].isoformat(),
    }


def _split_frame(timestamp_count: int, symbols: list[str]) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2026-02-01", periods=timestamp_count, freq="min", tz="UTC"
    )
    return pd.DataFrame(
        {
            "time": timestamps.repeat(len(symbols)),
            "symbol": symbols * timestamp_count,
            "timeframe": "1m",
            "profit_barrier_first": 1.0,
        }
    )


def test_split_rejects_empty_unique_timestamp_partitions_despite_many_rows():
    frame = _split_frame(3, [f"SYMBOL_{index}" for index in range(100)])

    with pytest.raises(ValueError, match="timestamp partitions"):
        DataPipeline(min_train_size=1).create_splits(frame, label_horizon=1)


@pytest.mark.parametrize(
    ("label_horizon", "target"),
    [(20, 1.0), (3, np.nan)],
    ids=["excessive-horizon", "unknown-targets"],
)
def test_split_rejects_empty_partitions_after_purge_or_target_filtering(
    label_horizon, target
):
    frame = _split_frame(100, ["EURUSD"])
    frame["profit_barrier_first"] = target

    with pytest.raises(ValueError, match="empty partitions"):
        DataPipeline(min_train_size=1).create_splits(
            frame, label_horizon=label_horizon
        )


def test_split_applies_minimum_train_size_after_purge_and_target_filtering():
    frame = _split_frame(100, ["EURUSD"])

    with pytest.raises(
        ValueError,
        match="Training partition too small.*57 rows.*minimum 58",
    ):
        DataPipeline(min_train_size=58).create_splits(frame, label_horizon=3)


def _factory_for_generation() -> ResearchFactory:
    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(generation=1)
    factory.source_roots = (Path("unused"),)
    factory.profit_barrier_pct = 0.02
    factory.loss_barrier_pct = 0.01
    factory.label_horizon = 3
    factory._log_event = lambda *args, **kwargs: None
    return factory


def test_generation_routes_exact_canonical_frame_and_only_training_partitions(
    monkeypatch,
):
    raw = pd.DataFrame({"raw": [1.0]})
    canonical = pd.DataFrame({"canonical": [2.0]})
    feature_set = FeatureSet(
        canonical=canonical,
        features=pd.DataFrame({"feature": [2.0]}),
        labels=pd.DataFrame({"profit_barrier_first": [1]}),
        feature_names=["feature"],
        label_names=["profit_barrier_first"],
        feature_metadata={},
    )
    train = pd.DataFrame({"partition": ["train"]})
    validation = pd.DataFrame({"partition": ["validation"]})
    test = pd.DataFrame({"partition": ["test"]})
    captures = {"hypotheses": 0, "walk_forward": 0}

    class RaisingSealedSplit:
        def __init__(self, train_frame, validation_frame, test_frame):
            self.train = train_frame
            self.validation = validation_frame
            self.test = test_frame
            self.split_info = {}

        @property
        def sealed_holdout(self):
            raise AssertionError("sealed holdout must remain inaccessible in Plan 1")

    class FakeDataPipeline:
        def load_sources(self, sources):
            captures["sources"] = sources
            return raw

        def compute_dataset_fingerprint(self, frame):
            captures["fingerprinted"] = frame
            return "canonical-fingerprint"

        def create_splits(self, frame, *, label_horizon):
            captures["split_frame"] = frame
            captures["label_horizon"] = label_horizon
            return RaisingSealedSplit(train, validation, test)

    class FakeFeatureEngineer:
        def engineer(self, frame, **kwargs):
            captures["engineer_frame"] = frame
            captures["engineer_kwargs"] = kwargs
            return feature_set

    class FakeMLPipeline:
        def train(self, train_frame, validation_frame):
            captures["training_frames"] = (train_frame, validation_frame)
            return [SimpleNamespace(feature_names=[])]

    factory = _factory_for_generation()
    factory.data_pipeline = FakeDataPipeline()
    factory.feature_engineer = FakeFeatureEngineer()
    factory.ml_pipeline = FakeMLPipeline()

    def forbidden_walk_forward(*args):
        captures["walk_forward"] += 1
        raise AssertionError("classification-only replay must not run")

    def forbidden_hypotheses():
        captures["hypotheses"] += 1
        raise AssertionError("hypotheses must not run without cost-aware replay")

    factory._walk_forward_validation = forbidden_walk_forward
    factory._generate_hypotheses_from_losses = forbidden_hypotheses
    source_catalog = [object()]
    monkeypatch.setattr(
        "aegis.research_factory.core.discover_csv_sources",
        lambda roots: source_catalog,
    )

    factory._run_generation()

    assert captures["sources"] is source_catalog
    assert captures["engineer_frame"] is raw
    assert captures["engineer_kwargs"] == {
        "profit_barrier_pct": 0.02,
        "loss_barrier_pct": 0.01,
        "label_horizon": 3,
    }
    assert captures["split_frame"] is feature_set.canonical
    assert captures["fingerprinted"] is feature_set.canonical
    assert captures["label_horizon"] == 3
    assert captures["training_frames"][0] is train
    assert captures["training_frames"][1] is validation
    assert factory.state.dataset_fingerprint == "canonical-fingerprint"
    assert factory.state.last_generation_status == "FAILED"
    assert "cost-aware replay" in factory.state.last_generation_reason.lower()
    assert captures["walk_forward"] == 0
    assert captures["hypotheses"] == 0
    assert not hasattr(factory, "_sealed_holdout")
    assert not hasattr(ResearchFactory, "_walk_forward_validation")


def test_generation_with_empty_source_catalog_records_no_data_and_stops(
    monkeypatch,
):
    calls = {"models": 0, "hypotheses": 0}

    class EmptyDataPipeline:
        def load_sources(self, sources):
            assert sources == []
            return pd.DataFrame()

    class ForbiddenMLPipeline:
        def train(self, *args):
            calls["models"] += 1
            raise AssertionError("training must not run without source data")

    factory = _factory_for_generation()
    factory.data_pipeline = EmptyDataPipeline()
    factory.feature_engineer = object()
    factory.ml_pipeline = ForbiddenMLPipeline()

    def generate_hypotheses():
        calls["hypotheses"] += 1
        return []

    factory._generate_hypotheses_from_losses = generate_hypotheses
    monkeypatch.setattr(
        "aegis.research_factory.core.discover_csv_sources", lambda roots: []
    )

    factory._run_generation()

    assert factory.state.last_generation_status == "NO_DATA"
    assert factory.state.last_generation_reason
    assert calls == {"models": 0, "hypotheses": 0}
    assert factory.state.hypothesis_registry == {}
    assert factory.state.experiments == []


def test_generation_training_failure_records_failed_and_stops(monkeypatch):
    canonical = pd.DataFrame({"canonical": [1.0]})
    train = pd.DataFrame({"partition": ["train"]})
    validation = pd.DataFrame({"partition": ["validation"]})
    test = pd.DataFrame({"partition": ["test"]})
    sealed = pd.DataFrame({"partition": ["sealed"]})
    calls = {"hypotheses": 0}

    class FakeDataPipeline:
        def load_sources(self, sources):
            return pd.DataFrame({"raw": [1.0]})

        def compute_dataset_fingerprint(self, frame):
            return "canonical-fingerprint"

        def create_splits(self, frame, *, label_horizon):
            return DatasetSplit(train, validation, test, sealed, {})

    class FailingMLPipeline:
        def train(self, train_frame, validation_frame):
            raise ValueError("single-class training target")

    factory = _factory_for_generation()
    factory.data_pipeline = FakeDataPipeline()
    factory.feature_engineer = SimpleNamespace(
        engineer=lambda *args, **kwargs: SimpleNamespace(canonical=canonical)
    )
    factory.ml_pipeline = FailingMLPipeline()

    def generate_hypotheses():
        calls["hypotheses"] += 1
        return []

    factory._generate_hypotheses_from_losses = generate_hypotheses
    monkeypatch.setattr(
        "aegis.research_factory.core.discover_csv_sources", lambda roots: [object()]
    )

    factory._run_generation()

    assert factory.state.last_generation_status == "FAILED"
    assert "single-class training target" in factory.state.last_generation_reason
    assert calls["hypotheses"] == 0
    assert factory.state.hypothesis_registry == {}
    assert factory.state.experiments == []


def test_generation_with_empty_model_list_records_failed_and_stops(monkeypatch):
    canonical = pd.DataFrame({"canonical": [1.0]})
    train = pd.DataFrame({"partition": ["train"]})
    validation = pd.DataFrame({"partition": ["validation"]})
    test = pd.DataFrame({"partition": ["test"]})
    calls = {"hypotheses": 0}

    class FakeDataPipeline:
        def load_sources(self, sources):
            return pd.DataFrame({"raw": [1.0]})

        def compute_dataset_fingerprint(self, frame):
            return "canonical-fingerprint"

        def create_splits(self, frame, *, label_horizon):
            return SimpleNamespace(train=train, validation=validation, test=test)

    factory = _factory_for_generation()
    factory.data_pipeline = FakeDataPipeline()
    factory.feature_engineer = SimpleNamespace(
        engineer=lambda *args, **kwargs: SimpleNamespace(canonical=canonical)
    )
    factory.ml_pipeline = SimpleNamespace(train=lambda *args: [])

    def generate_hypotheses():
        calls["hypotheses"] += 1
        return []

    factory._generate_hypotheses_from_losses = generate_hypotheses
    monkeypatch.setattr(
        "aegis.research_factory.core.discover_csv_sources", lambda roots: [object()]
    )

    factory._run_generation()

    assert factory.state.last_generation_status == "FAILED"
    assert "no trained models" in factory.state.last_generation_reason.lower()
    assert calls["hypotheses"] == 0


@pytest.mark.parametrize("failure_stage", ["fingerprint", "split"])
def test_generation_classifies_malformed_preparation_as_failed(
    monkeypatch, failure_stage
):
    canonical = _split_frame(100, ["EURUSD"])
    calls = {"models": 0}

    class MalformedDataPipeline:
        def load_sources(self, sources):
            return pd.DataFrame({"raw": [1.0]})

        def compute_dataset_fingerprint(self, frame):
            if failure_stage == "fingerprint":
                raise ValueError("malformed fingerprint input")
            return "canonical-fingerprint"

        def create_splits(self, frame, *, label_horizon):
            raise ValueError("malformed split input")

    class ForbiddenMLPipeline:
        def train(self, *args):
            calls["models"] += 1
            raise AssertionError("training must not run after malformed preparation")

    factory = _factory_for_generation()
    factory.data_pipeline = MalformedDataPipeline()
    factory.feature_engineer = SimpleNamespace(
        engineer=lambda *args, **kwargs: SimpleNamespace(canonical=canonical)
    )
    factory.ml_pipeline = ForbiddenMLPipeline()
    monkeypatch.setattr(
        "aegis.research_factory.core.discover_csv_sources", lambda roots: [object()]
    )

    factory._run_generation()

    assert factory.state.last_generation_status == "FAILED"
    assert "malformed" in factory.state.last_generation_reason
    assert calls["models"] == 0


def test_generation_classifies_genuinely_insufficient_split_as_no_data(monkeypatch):
    canonical = _split_frame(3, ["EURUSD"])

    class InsufficientDataPipeline(DataPipeline):
        def __init__(self):
            super().__init__(min_train_size=1)

        def load_sources(self, sources):
            return pd.DataFrame({"raw": [1.0]})

        def compute_dataset_fingerprint(self, frame):
            return "canonical-fingerprint"

    factory = _factory_for_generation()
    factory.data_pipeline = InsufficientDataPipeline()
    factory.feature_engineer = SimpleNamespace(
        engineer=lambda *args, **kwargs: SimpleNamespace(canonical=canonical)
    )
    factory.ml_pipeline = SimpleNamespace(
        train=lambda *args: (_ for _ in ()).throw(
            AssertionError("training must not run without usable splits")
        )
    )
    monkeypatch.setattr(
        "aegis.research_factory.core.discover_csv_sources", lambda roots: [object()]
    )

    factory._run_generation()

    assert factory.state.last_generation_status == "NO_DATA"
    assert factory.state.last_generation_reason


def test_generation_clears_prior_terminal_outcome_before_new_work(monkeypatch):
    observed_outcomes = []
    factory = _factory_for_generation()
    factory.state.last_generation_status = "CHALLENGER"
    factory.state.last_generation_reason = "prior generation"

    class EmptyDataPipeline:
        def load_sources(self, sources):
            observed_outcomes.append(
                (
                    factory.state.last_generation_status,
                    factory.state.last_generation_reason,
                )
            )
            return pd.DataFrame()

    factory.data_pipeline = EmptyDataPipeline()
    factory.feature_engineer = object()
    factory.ml_pipeline = object()
    monkeypatch.setattr(
        "aegis.research_factory.core.discover_csv_sources", lambda roots: []
    )

    factory._run_generation()

    assert observed_outcomes == [("", "")]
    assert factory.state.last_generation_status == "NO_DATA"
