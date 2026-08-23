from __future__ import annotations

import json

import numpy as np
import pandas as pd

from aegis.research_factory.data import DataPipeline, discover_csv_sources


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

    assert pipeline.compute_dataset_fingerprint(frame) == (
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
