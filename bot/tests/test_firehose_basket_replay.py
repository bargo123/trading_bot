from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from aegis.research.books_index import BookIndex
from aegis.research.firehose_basket_evidence import build_evidence_packet
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


_TRUSTED_INDEX = None


@pytest.fixture(autouse=True)
def _trusted_book_index(tmp_path, monkeypatch):
    global _TRUSTED_INDEX
    books = tmp_path / "books"
    books.mkdir()
    (books / "trusted.md").write_bytes(
        b"# Trusted\nUse a volume spike to confirm a breakout.\n"
        b"Avoid a failed breakout after a volume spike.\n",
    )
    index = BookIndex(tmp_path / "books.sqlite")
    index.rebuild(books)
    _TRUSTED_INDEX = index
    monkeypatch.setattr("aegis.research.firehose_basket_replay.BookIndex", lambda: index, raising=False)
    yield
    _TRUSTED_INDEX = None


def _policy_packets():
    assert _TRUSTED_INDEX is not None
    return {
        policy: {
            **build_evidence_packet(
                _TRUSTED_INDEX,
                {"hypothesis_id": f"basket:{policy}", "origin": "BOOK_DIRECT"},
                "volume spike",
                "failed breakout",
                {"source": "recorded"},
                "Reject on incomplete sealed OOS evidence.",
            ),
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
        "features": {
            "momentum": {"value": 0.5, "available_at": timestamp},
        },
        "lifecycle": {
            "basket_id": f"basket-{timestamp}",
            "ticket_id": f"ticket-{timestamp}",
            "opened_at": timestamp - 0.5,
            "closed_at": timestamp,
            "confirmed_close": True,
            "mfe_usd": 1.0,
            "mae_usd": -0.2,
            "peak_net_profit_usd": 1.0,
            "realized_net_usd": 0.5,
            "capture_ratio": 0.5,
            "age_seconds": 0.5,
            "clips": 1,
            "decision_reasons": ["recorded"],
            "ev": 0.1,
            "cost_usd": 0.2,
            "regime": "trend",
            "session": "london",
            "turnover": 1.0,
        },
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


def test_rejects_features_that_were_not_available_at_the_row_timestamp():
    rows = _rows()
    rows[2]["features"]["momentum"]["available_at"] = 4

    result = evaluate_basket_policies(rows, _policy_packets())

    assert result == {"status": "NO_EVIDENCE", "reason": "future_feature_evidence"}


def test_requires_a_confirmed_complete_lifecycle_for_every_row():
    rows = _rows()
    del rows[0]["lifecycle"]

    result = evaluate_basket_policies(rows, _policy_packets())

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_lifecycle_evidence"}


@pytest.mark.parametrize(
    ("collection", "record"),
    [
        ("supporting_evidence", {"evidence_label": "SUPPORT", "location": {}, "passage": "support"}),
        ("supporting_evidence", {"source_id": "source", "location": {}, "passage": "support"}),
        ("supporting_evidence", {"source_id": "source", "evidence_label": "SUPPORT", "location": {}}),
        ("contradicting_evidence", {"source_id": "source", "evidence_label": "CONTRADICTION", "location": {}, "passage": "risk"}),
    ],
)
def test_rejects_book_evidence_without_complete_verbatim_provenance(collection, record):
    packets = _policy_packets()
    packets["structural"][collection] = [record]

    result = evaluate_basket_policies(_rows(), packets)

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_policy_evidence"}


def test_rejects_provenance_with_a_fabricated_digest_for_the_declared_source():
    packets = _policy_packets()
    packets["structural"]["supporting_evidence"][0]["file_hash"] = "f" * 64
    packets["structural"]["supporting_evidence"][0]["source_id"] = "f" * 64

    result = evaluate_basket_policies(_rows(), packets)

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_policy_evidence"}


def test_rejects_a_self_consistent_source_that_is_not_in_the_trusted_index(tmp_path):
    attacker = tmp_path / "attacker.md"
    attacker.write_text("Fabricated support.\n", encoding="utf-8")
    body = attacker.read_bytes()
    packets = _policy_packets()
    packets["structural"]["supporting_evidence"][0].update({
        "filename": attacker.name,
        "file_hash": sha256(body).hexdigest(),
        "source_id": sha256(body).hexdigest(),
        "location": {"path": str(attacker), "line_start": 1, "line_end": 1},
        "passage": "Fabricated support.",
    })

    result = evaluate_basket_policies(_rows(), packets)

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_policy_evidence"}


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
    for row in rows:
        if row["partition"] == "TRAIN":
            row["policy_outcomes"]["harvest"]["gross_pnl_usd"] = 1.2

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


def test_selects_the_winner_from_realized_walk_forward_outcomes():
    rows = _rows()
    for row in rows:
        for policy in POLICIES:
            row["policy_outcomes"][policy]["gross_pnl_usd"] = 0.3
    for row in rows:
        if row["partition"] == "TRAIN":
            row["policy_outcomes"]["structural"]["gross_pnl_usd"] = 100.2
        elif row["partition"] == "VALIDATION":
            row["policy_outcomes"]["harvest"]["gross_pnl_usd"] = 20.2

    result = evaluate_basket_policies(rows, _policy_packets())

    assert result["winner"] == "structural"
    assert [decision["winner"] for decision in result["walk_forward"]] == ["structural"] * 4
    assert [decision["costed_return_r"] for decision in result["walk_forward"]] == pytest.approx([0.1] * 4)
    assert result["walk_forward_metrics"]["expectancy_r"] == pytest.approx(0.1)
