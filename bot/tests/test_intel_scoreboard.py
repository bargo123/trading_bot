from aegis.intel.scoreboard import summarize_journal


def test_scoreboard_separates_old_flatten_from_intelligent_exits():
    rows = [
        {"event": "flatten", "reason": "quick_win", "pnl": 0.01},
        {"event": "flatten", "reason": "quick_win", "pnl": 0.01},
        {"event": "flatten", "reason": "quick_win", "pnl": -1.10},
        {"event": "intel_brain_fire", "action": "fire"},
        {"event": "intel_brain_skip", "action": "skip", "reason": "unacceptable_uncertainty"},
        {"event": "intel_brain_exit", "action": "exit", "pnl": 0.12, "brain": "intelligent_firehose"},
    ]
    summary = summarize_journal(rows)
    assert summary["old"]["closes"] == 3
    assert summary["intelligent"]["fires"] == 1
    assert summary["intelligent"]["closes"] == 1
    assert summary["target_gap"]["objective_usd_per_day"] == 100.0
