from __future__ import annotations

import pandas as pd
import pytest

from aegis.research.reports import book_compliance_matrix, capability_matrix
from aegis.research.train import named_always_take_baseline


def test_stack_run_is_not_labeled_as_firehose_benchmark():
    trained = {
        "always_take_n": 67,
        "always_take_expectancy": -0.125,
        "always_take_profit_factor": 0.37,
    }
    row = named_always_take_baseline(trained, kind="stack")
    assert row["name"] == "six_book_stack_always_take"
    assert "firehose" not in row["name"]
    fire = named_always_take_baseline(trained, kind="bars")
    assert fire["name"] == "legacy_firehose_always_take"


def test_harris_jump_live_capability_has_proof():
    rows = {r["capability"]: r for r in capability_matrix()}
    proof = str(rows["harris_jump_live"]["proof"])
    assert proof.strip()
    assert "harris" in proof.lower()


def test_book_compliance_does_not_duplicate_named_six_books():
    rows = book_compliance_matrix()
    names = [r["book"] for r in rows]
    assert names.count("johnson") == 0
    assert names.count("gann") == 0
    assert names.count("prado") == 0
    assert any("Gann" in n for n in names)
    assert any("Johnson DMA" in n for n in names)


def test_triple_barrier_labels_pt_sl_and_vertical():
    from aegis.research.prado import triple_barrier_label

    up = pd.Series([1.00, 1.01, 1.03, 1.04])
    assert triple_barrier_label(up, pt=0.02, sl=0.02, max_bars=3) == 1.0
    dn = pd.Series([1.00, 0.99, 0.97, 0.96])
    assert triple_barrier_label(dn, pt=0.02, sl=0.02, max_bars=3) == -1.0
    flat = pd.Series([1.00, 1.001, 1.002, 1.001])
    assert triple_barrier_label(flat, pt=0.05, sl=0.05, max_bars=2) == 0.0


def test_combinatorial_purged_folds_keep_time_order():
    from aegis.research.evaluate import combinatorial_purged_folds

    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-06-01", periods=50, freq="h", tz="UTC"),
            "pnl": [0.01] * 50,
        }
    )
    folds = list(combinatorial_purged_folds(df, n_groups=5, n_test_groups=1, embargo_frac=0.02))
    assert len(folds) == 5
    for train, test in folds:
        train_t = pd.to_datetime(train["time"], utc=True)
        test_t = pd.to_datetime(test["time"], utc=True)
        assert not (set(train_t) & set(test_t))
        embargo = (test_t.max() - test_t.min()) * 0.02
        lo = test_t.min() - embargo
        hi = test_t.max() + embargo
        inside = train_t[(train_t >= lo) & (train_t <= hi)]
        assert inside.empty


def test_default_calendar_file_is_on_disk_and_point_in_time():
    from aegis.research.news import DEFAULT_CALENDAR_PATH, load_calendar_file

    events = load_calendar_file(DEFAULT_CALENDAR_PATH)
    assert len(events) >= 4
    for ev in events:
        assert ev["as_of_utc"] <= ev["event_utc"]
        assert ev["impact"] in {"high", "3"}
