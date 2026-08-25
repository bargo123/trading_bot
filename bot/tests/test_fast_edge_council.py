from __future__ import annotations

import json

import review_fast_edge_council as council
from review_fast_edge_council import _bounded_evidence, _prompt


def test_council_evidence_stays_bounded_and_valid_json():
    report = {
        "EXECUTION_STATUS": "SHADOW_ONLY_NO_POSITIVE_OOS",
        "candidate_rows": 329950,
        "symbols": ["EURUSD", "GBPJPY"],
        "horizons_s": [1, 2, 3, 5, 8, 10, 15, 20, 30, 45],
        "leaderboard_top_50": [
            {"symbol": "EURUSD", "captured_exit_expectancy": 0.001, "noise": "x" * 10000}
            for _ in range(50)
        ],
        "exit_policy_comparison": [{"symbol": "EURUSD", "noise": "x" * 10000} for _ in range(50)],
        "book_evidence": [{"query": "scalping", "sources": ["x"] * 10000}],
        "multi_outcome_models": {"probability": {"P_GREEN_1S": {"oos_n": 100}}},
        "fast_winner_feature_discovery": {
            "analysis_scope": "descriptive_sealed_oos",
            "horizons": {"1": {"fast_clean_n": 12, "slow_or_losing_n": 88, "top_feature_differences": []}},
        },
        "spread_vol_gate_sweep": [
            {"spread_to_realized_vol_max": 0.2, "spread_to_micro_vol_max": 1.5, "sealed": {"selected": 12}},
        ],
        "model_space": {"promotion_candidates": [{"noise": "x" * 10000}]},
    }
    evidence = _bounded_evidence(report)
    assert len(evidence) <= 6000
    bounded = json.loads(evidence)
    assert bounded["status"] == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert bounded["fast_winner_feature_discovery"]["analysis_scope"] == "descriptive_sealed_oos"
    assert bounded["spread_vol_gate_sweep"][0]["sealed"]["selected"] == 12
    assert len(_prompt(report, role="ML CRITIC")) < 8000


def test_swarm_dispatches_all_roles_across_configured_free_models(monkeypatch):
    calls = []
    monkeypatch.setattr(
        council,
        "load_agents_config",
        lambda: {"hermes": {"models": ["free-a", "free-b", "free-c"]}},
    )

    def fake_ask(prompt, *, model, timeout_s):
        calls.append((model, timeout_s, prompt))
        return {"status": "AVAILABLE", "ok": True, "duration_s": 0.01, "parsed": {"hypotheses": []}}

    monkeypatch.setattr(council.hermes_adapter, "ask", fake_ask)
    result = council._run_hermes_swarm({"EXECUTION_STATUS": "SHADOW_ONLY"}, timeout_s=30)
    assert len(calls) == len(council.ROLES)
    assert {call[0] for call in calls} == {"free-a", "free-b", "free-c"}
    assert result["status"] == "AVAILABLE"
    assert len(result["requests"]) == len(council.ROLES)
