from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aegis.engines.base import Bar
from scripts.run_video_style_paper import collect_mt5_bars, main


def _write_bars(path: Path) -> None:
    pd.DataFrame(
        [
            (0, 100.0, 100.5, 99.5, 100.0),
            (1, 100.0, 102.0, 99.5, 101.5),
            (2, 101.5, 105.0, 101.0, 104.0),
            (3, 104.0, 109.0, 103.0, 108.0),
        ],
        columns=["time", "open", "high", "low", "close"],
    ).to_csv(path, index=False)


def test_cli_writes_truthful_all_symbol_artifacts(tmp_path: Path):
    bars_dir = tmp_path / "bars"
    output_dir = tmp_path / "reports"
    bars_dir.mkdir()
    _write_bars(bars_dir / "EURUSD.csv")
    _write_bars(bars_dir / "SILVER.csv")

    assert main(["--bars-dir", str(bars_dir), "--output-dir", str(output_dir)]) == 0

    result = json.loads((output_dir / "video_style_paper_result.json").read_text())
    assert result["placed_orders"] is False
    assert set(result["per_symbol"]) == {"EURUSD", "SILVER"}
    assert (output_dir / "video_style_paper_trades.csv").exists()
    assert "placed_orders: false" in (output_dir / "video_style_paper_summary.md").read_text()


def test_cli_accepts_seconds_horizon(tmp_path: Path):
    bars_dir = tmp_path / "bars"
    output_dir = tmp_path / "reports"
    bars_dir.mkdir()
    pd.DataFrame(
        [
            ("2026-01-01T00:00:00Z", 100.0, 100.5, 99.5, 100.0),
            ("2026-01-01T00:00:01Z", 100.0, 102.0, 99.5, 101.5),
            ("2026-01-01T00:00:02Z", 101.5, 101.8, 101.2, 101.6),
            ("2026-01-01T00:00:05Z", 101.6, 101.8, 101.4, 101.7),
        ],
        columns=["time", "open", "high", "low", "close"],
    ).to_csv(bars_dir / "EURUSD.csv", index=False)

    assert main([
        "--bars-dir", str(bars_dir), "--output-dir", str(output_dir),
        "--max-hold-s", "3",
    ]) == 0
    result = json.loads((output_dir / "video_style_paper_result.json").read_text())
    assert result["trades"][0]["exit_reason"] == "time"


def test_cli_rejects_malformed_input_without_success_artifacts(tmp_path: Path):
    bars_dir = tmp_path / "bars"
    output_dir = tmp_path / "reports"
    bars_dir.mkdir()
    pd.DataFrame({"time": [0], "close": [1.0]}).to_csv(bars_dir / "BROKEN.csv", index=False)

    assert main(["--bars-dir", str(bars_dir), "--output-dir", str(output_dir)]) == 1
    assert not (output_dir / "video_style_paper_result.json").exists()


class _ReadonlyFakeEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self.mutations = 0

    def bars(self, symbol: str, timeframe: str, lookback_days: int) -> list[Bar]:
        self.calls.append((symbol, timeframe, lookback_days))
        return [
            Bar(0, 100.0, 100.5, 99.5, 100.0),
            Bar(1, 100.0, 102.0, 99.5, 101.5),
            Bar(2, 101.5, 105.0, 101.0, 104.0),
        ]

    def place_order(self, *args, **kwargs):
        self.mutations += 1
        raise AssertionError("paper feed must not place broker orders")


def test_mt5_feed_collects_all_symbols_through_readonly_bar_interface():
    engine = _ReadonlyFakeEngine()

    frames = collect_mt5_bars(engine, ["EURUSD", "SILVER"], "M1", 30)

    assert set(frames) == {"EURUSD", "SILVER"}
    assert all(list(frame.columns) == ["time", "open", "high", "low", "close"] for frame in frames.values())
    assert engine.calls == [("EURUSD", "M1", 30), ("SILVER", "M1", 30)]
    assert engine.mutations == 0
