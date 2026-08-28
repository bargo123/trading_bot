"""Monotonic scheduling and telemetry for cooperative Firehose checkpoints."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ScanProgress:
    symbol_index: int
    symbol_count: int
    cycle_started_mono: float


class RuntimeCheckpointState:
    """Track checkpoint cadence without owning broker or strategy behavior."""

    def __init__(self, interval_s: float, max_samples: int = 1024) -> None:
        interval = float(interval_s)
        if not math.isfinite(interval):
            raise ValueError("interval_s must be finite")
        self.interval_s = max(0.05, interval)
        self._last_mono: float | None = None
        self._last_wall: float | None = None
        self._last_progress: ScanProgress | None = None
        self._last_gap_ms: float | None = None
        self._gaps_ms: deque[float] = deque(maxlen=max(1, int(max_samples)))
        self._open_ticket_rechecks = 0
        self._confirmed_closes = 0
        self._last_close_to_rescan_ms: float | None = None

    def due(self, now_mono: float) -> bool:
        now = float(now_mono)
        if not math.isfinite(now):
            raise ValueError("now_mono must be finite")
        return self._last_mono is None or now - self._last_mono >= self.interval_s

    def record(
        self,
        now_mono: float,
        now_wall: float,
        progress: ScanProgress,
        *,
        open_ticket_rechecks: int = 0,
        confirmed_closes: int = 0,
        close_to_rescan_ms: float | None = None,
    ) -> dict[str, object]:
        now = float(now_mono)
        wall = float(now_wall)
        cycle_started = float(progress.cycle_started_mono)
        if not all(math.isfinite(value) for value in (now, wall, cycle_started)):
            raise ValueError("checkpoint times must be finite")
        if self._last_mono is not None:
            self._last_gap_ms = max(0.0, (now - self._last_mono) * 1000.0)
            self._gaps_ms.append(self._last_gap_ms)
        self._last_mono = now
        self._last_wall = wall
        self._last_progress = progress
        self._open_ticket_rechecks += max(0, int(open_ticket_rechecks))
        self._confirmed_closes += max(0, int(confirmed_closes))
        if close_to_rescan_ms is not None:
            value = float(close_to_rescan_ms)
            if not math.isfinite(value):
                raise ValueError("close_to_rescan_ms must be finite")
            self._last_close_to_rescan_ms = max(0.0, value)
        return self.snapshot(now_mono=now)

    def snapshot(self, *, now_mono: float | None = None) -> dict[str, object]:
        current = self._last_mono if now_mono is None else float(now_mono)
        if current is None:
            current = 0.0
        if not math.isfinite(current):
            raise ValueError("now_mono must be finite")
        sorted_gaps = sorted(self._gaps_ms)
        p95 = (
            sorted_gaps[int(0.95 * (len(sorted_gaps) - 1))]
            if sorted_gaps else None
        )
        progress = self._last_progress or ScanProgress(0, 0, current)
        return {
            "LAST_RUNTIME_CHECKPOINT_AT": self._last_wall,
            "RUNTIME_CHECKPOINT_GAP_MS": self._last_gap_ms,
            "RUNTIME_CHECKPOINT_GAP_P95_MS": p95,
            "OPEN_TICKET_RECHECKS": self._open_ticket_rechecks,
            "CONFIRMED_CLOSES_FINALIZED": self._confirmed_closes,
            "CLOSE_TO_RESCAN_MS": self._last_close_to_rescan_ms,
            "SCAN_SYMBOL_INDEX": int(progress.symbol_index),
            "SCAN_SYMBOL_COUNT": int(progress.symbol_count),
            "SCAN_CYCLE_AGE_MS": max(
                0.0, (current - float(progress.cycle_started_mono)) * 1000.0
            ),
        }
