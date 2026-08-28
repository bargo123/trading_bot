from __future__ import annotations

import pytest

from aegis.intel.runtime_checkpoint import RuntimeCheckpointState, ScanProgress


def test_checkpoint_due_uses_monotonic_elapsed_time():
    state = RuntimeCheckpointState(interval_s=1.0)

    assert state.due(10.0)
    state.record(10.0, 1000.0, ScanProgress(1, 26, 9.0))

    assert not state.due(10.999)
    assert state.due(11.0)


def test_checkpoint_snapshot_reports_gap_and_scan_progress():
    state = RuntimeCheckpointState(interval_s=1.0)
    state.record(
        10.0,
        1000.0,
        ScanProgress(3, 26, 7.0),
        open_ticket_rechecks=2,
    )

    snapshot = state.record(
        11.25,
        1001.25,
        ScanProgress(4, 26, 7.0),
        open_ticket_rechecks=1,
        confirmed_closes=1,
        close_to_rescan_ms=40.0,
    )

    assert snapshot["LAST_RUNTIME_CHECKPOINT_AT"] == 1001.25
    assert snapshot["RUNTIME_CHECKPOINT_GAP_MS"] == pytest.approx(1250.0)
    assert snapshot["RUNTIME_CHECKPOINT_GAP_P95_MS"] == pytest.approx(1250.0)
    assert snapshot["OPEN_TICKET_RECHECKS"] == 3
    assert snapshot["CONFIRMED_CLOSES_FINALIZED"] == 1
    assert snapshot["CLOSE_TO_RESCAN_MS"] == pytest.approx(40.0)
    assert snapshot["SCAN_SYMBOL_INDEX"] == 4
    assert snapshot["SCAN_SYMBOL_COUNT"] == 26
    assert snapshot["SCAN_CYCLE_AGE_MS"] == pytest.approx(4250.0)


def test_checkpoint_rejects_non_finite_time():
    state = RuntimeCheckpointState(interval_s=1.0)

    with pytest.raises(ValueError, match="finite"):
        state.record(float("nan"), 1000.0, ScanProgress(1, 26, 0.0))
