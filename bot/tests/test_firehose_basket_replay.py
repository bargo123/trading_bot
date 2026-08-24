from copy import deepcopy

from aegis.research.firehose_basket_replay import evaluate_basket_policies


POLICIES = (
    "structural",
    "harvest",
    "extension",
    "floor",
    "ev",
    "scratch",
    "combined",
)


def _policy_packets():
    return {
        policy: {
            "hypothesis_id": f"basket:{policy}",
            "origin": "BOOK_DIRECT",
            "BOOK_COVERAGE": "SUFFICIENT",
            "supporting_evidence": [{"source_id": f"source:{policy}"}],
            "data_observation": {"source": "recorded"},
            "falsification": "Reject on incomplete sealed OOS evidence.",
            "normalized_parameters": {
                "r_multiple": 1.0,
                "cost_r": 0.1,
                "momentum_threshold": 0.5,
            },
        }
        for policy in POLICIES
    }


def _row(timestamp, partition, gross_pnl):
    return {
        "timestamp": timestamp,
        "partition": partition,
        "initial_risk_usd": 1.0,
        "cost_usd": 0.2,
        "capture_ratio": 0.5,
        "turnover": 1.0,
        "policy_outcomes": {
            policy: {"gross_pnl_usd": value} for policy, value in gross_pnl.items()
        },
    }


def _rows():
    return [
        _row(1, "TRAIN", {policy: 1.2 for policy in POLICIES}),
        _row(2, "TRAIN", {policy: 0.8 for policy in POLICIES}),
        _row(3, "VALIDATION", {policy: 1.2 for policy in POLICIES}),
        _row(4, "VALIDATION", {policy: 0.8 for policy in POLICIES}),
        _row(5, "VALIDATION", {policy: 1.1 for policy in POLICIES}),
        _row(6, "VALIDATION", {policy: 0.9 for policy in POLICIES}),
        _row(7, "OOS", {policy: 1.0 for policy in POLICIES}),
        _row(8, "SEALED", {policy: 0.8 for policy in POLICIES}),
    ]


def test_rejects_rows_that_are_not_strictly_chronological():
    rows = _rows()
    rows[2]["timestamp"] = 1

    result = evaluate_basket_policies(rows, _policy_packets())

    assert result == {"status": "NO_EVIDENCE", "reason": "non_chronological_rows"}


def test_requires_recorded_cost_evidence_for_every_row():
    rows = _rows()
    del rows[1]["cost_usd"]

    result = evaluate_basket_policies(rows, _policy_packets())

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_cost_evidence"}


def test_oos_and_sealed_rows_do_not_change_the_validation_winner():
    rows = _rows()
    for row in rows:
        for policy in POLICIES:
            row["policy_outcomes"][policy]["gross_pnl_usd"] = 0.3
        row["policy_outcomes"]["structural"]["gross_pnl_usd"] = 1.2
    for row in rows:
        if row["partition"] not in {"OOS", "SEALED"}:
            continue
        row["policy_outcomes"]["structural"]["gross_pnl_usd"] = -10.0
        row["policy_outcomes"]["harvest"]["gross_pnl_usd"] = 10.0

    result = evaluate_basket_policies(rows, _policy_packets())

    assert result["winner"] == "structural"
    assert result["oos_metrics"]["expectancy_r"] == -10.2
    assert result["artifact"] == {
        "validated": True,
        "complete": True,
        "policy": "structural",
        "normalized_parameters": {
            "r_multiple": 1.0,
            "cost_r": 0.1,
            "momentum_threshold": 0.5,
        },
    }


def test_returns_no_evidence_when_a_required_policy_packet_is_missing():
    packets = _policy_packets()
    del packets["scratch"]

    result = evaluate_basket_policies(_rows(), packets)

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_policy_evidence"}


def test_selects_by_costed_pf_tail_and_drawdown_not_win_rate():
    rows = _rows()
    for row in rows:
        for policy in POLICIES:
            row["policy_outcomes"][policy]["gross_pnl_usd"] = 0.0
    for row, structural, harvest in zip(
        (row for row in rows if row["partition"] == "VALIDATION"),
        (0.8, 0.8, 0.8, -1.6),
        (1.2, -0.8, 1.2, -0.8),
    ):
        row["policy_outcomes"]["structural"]["gross_pnl_usd"] = structural
        row["policy_outcomes"]["harvest"]["gross_pnl_usd"] = harvest

    result = evaluate_basket_policies(rows, _policy_packets())

    assert result["winner"] == "harvest"
    assert result["validation_metrics"]["win_rate"] == 0.5
    assert result["validation_metrics"]["expectancy_r"] == 0.0
    assert result["validation_metrics"]["profit_factor"] == 1.0
    assert result["validation_metrics"]["tail_r"] == -1.0
    assert result["validation_metrics"]["max_drawdown_r"] == 1.0


def test_omits_artifact_when_selected_policy_lacks_complete_oos_evidence():
    rows = deepcopy(_rows())
    for row in rows:
        for policy in POLICIES:
            row["policy_outcomes"][policy]["gross_pnl_usd"] = 0.3
        row["policy_outcomes"]["structural"]["gross_pnl_usd"] = 1.2
    del rows[-1]["policy_outcomes"]["structural"]

    result = evaluate_basket_policies(rows, _policy_packets())

    assert result == {"status": "NO_EVIDENCE", "reason": "incomplete_oos_evidence"}
