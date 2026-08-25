"""Run bounded research-only Hermes review, with optional Claude escalation."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))

from ai_council import hermes as hermes_adapter  # noqa: E402
from ai_council.agents import load_agents_config  # noqa: E402


ROLES = (
    "MICROSTRUCTURE RESEARCHER",
    "FAST-WINNER ANALYST",
    "LOSS AUTOPSY ANALYST",
    "FEATURE DISCOVERY AGENT",
    "BOOK RESEARCHER",
    "ML CRITIC",
    "CONTRARIAN",
    "TAIL LOSS ANALYST",
    "EXIT RESEARCHER",
    "STRATEGY SYNTHESIS AGENT",
)


_CANDIDATE_FIELDS = (
    "symbol", "side", "session", "regime", "structure", "family", "horizon_s",
    "model", "threshold", "exit_policy", "captured_exit_expectancy", "captured_exit_pf",
    "precision", "p95_loss", "p99_loss", "trades_per_hour", "candidate_arrivals_per_hour",
    "executable_trades_per_hour", "executable_net_per_hour", "median_time_to_green_s",
)


def _bounded_evidence(report: dict, *, candidate_limit: int = 6) -> str:
    """Serialize measured evidence below Windows' command-line argument limit."""
    model_space = report.get("model_space") or {}
    candidates = []
    for row in (report.get("leaderboard_top_50") or [])[:candidate_limit]:
        candidates.append(
            {
                key: row.get(key)
                for key in (*_CANDIDATE_FIELDS, "n", "win_rate", "avg_win", "avg_loss", "net_per_hour")
                if key in row
            }
        )
    exit_rows = []
    for row in (report.get("exit_policy_comparison") or [])[:6]:
        exit_rows.append(
            {
                key: row.get(key)
                for key in (
                    "symbol", "side", "session", "regime", "structure", "family", "horizon_s",
                    "exit_policy", "n", "win_rate", "captured_exit_expectancy", "captured_exit_pf",
                    "p95_loss", "p99_loss", "median_exit_time_s", "trades_per_hour", "net_per_hour",
                )
                if key in row
            }
        )
    book_rows = []
    for item in (report.get("book_evidence") or [])[:4]:
        book_rows.append(
            {
                key: item.get(key)
                for key in ("query", "mechanism", "hypothesis", "data_requirements", "limitations")
                if key in item
            }
        )
    outcome_summary = {}
    for family, values in (report.get("multi_outcome_models") or {}).items():
        if not isinstance(values, dict):
            continue
        outcome_summary[family] = {}
        for target, value in list(values.items())[:20]:
            if isinstance(value, dict):
                outcome_summary[family][target] = {
                    key: value.get(key)
                    for key in (
                        "status", "target_column", "model", "oos_n", "oos_positive_rate",
                        "oos_probability_mean", "oos_brier", "calibration_ece",
                    )
                    if key in value
                }
    payload = {
        "status": report.get("EXECUTION_STATUS"),
        "rows": report.get("candidate_rows"),
        "symbols": report.get("symbols"),
        "horizons_s": report.get("horizons_s"),
        "progress": {
            "shadow_trades_evaluated": report.get("shadow_trades_evaluated"),
            "models_tested": len(report.get("models_tested") or []),
            "features_tested": len(report.get("features_tested") or []),
            **{
                key: report.get(key)
                for key in (
                    "best_pf", "best_expectancy", "best_wr", "best_tail_loss",
                    "best_trades_per_hour", "best_time_to_green",
                )
                if key in report
            },
        },
        "top_candidates": candidates,
        "exit_policy_comparison": exit_rows,
        "multi_outcome": outcome_summary,
        "book_evidence": book_rows,
        "promotion_candidates": (model_space.get("promotion_candidates") or [])[:4],
    }
    encoded = json.dumps(payload, separators=(",", ":"), default=str)
    if len(encoded) <= 1400:
        return encoded
    # Keep a valid, compact JSON payload even if a future report grows.
    return json.dumps(
        {
            "status": report.get("EXECUTION_STATUS"),
            "rows": report.get("candidate_rows"),
            "symbols": report.get("symbols"),
            "horizons_s": report.get("horizons_s"),
            "progress": payload["progress"],
            "top_candidates": candidates[:1],
            "exit_policy_comparison": exit_rows[:1],
        },
        separators=(",", ":"),
        default=str,
    )


def _prompt(report: dict, *, role: str) -> str:
    model_space = report.get("model_space") or {}
    return (
        "You are a research-only quant council. Do not execute commands, edit files, access MT5, "
        "place orders, change config, or authorize a trade. Analyze the supplied measured shadow evidence.\n\n"
        f"Your assigned role: {role}. Other roles in this bounded swarm are: {', '.join(ROLES)}.\n"
        "Return JSON with keys: hypotheses (falsifiable, each with required features and rejection gate), "
        "loss_autopsies, exit_recommendations, feature_tests, book_contradictions, and next_experiments. "
        "Reject selection bias, tiny samples, calibration failures, and any result lacking chronological and sealed OOS.\n\n"
        + _bounded_evidence(report)
    )


def _run_hermes_swarm(
    report: dict,
    *,
    timeout_s: int,
    model_override: list[str] | None = None,
    role_override: list[str] | None = None,
) -> dict:
    models = [
        str(model).strip()
        for model in (
            model_override
            if model_override is not None
            else ((load_agents_config().get("hermes") or {}).get("models") or [])
        )
        if str(model).strip()
    ]
    roles = tuple(role_override or ROLES)
    if not models:
        return {"status": "UNAVAILABLE_CLI", "models_requested": [], "requests": []}
    requests = []
    for index, role in enumerate(roles):
        model = models[index % len(models)]
        result = hermes_adapter.ask(
            _prompt(report, role=role),
            model=model,
            timeout_s=timeout_s,
        )
        requests.append(
            {
                "role": role,
                "model": model,
                "status": result.get("status"),
                "ok": bool(result.get("ok")),
                "duration_s": result.get("duration_s"),
                "parsed": result.get("parsed"),
                "error": result.get("error"),
            }
        )
    available = [item for item in requests if item["ok"]]
    return {
        "status": "AVAILABLE" if available else "ERROR",
        "models_requested": models,
        "roles_requested": list(roles),
        "models_answered": sorted({item["model"] for item in available}),
        "requests": requests,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report", type=Path,
        default=BOT_ROOT / "reports" / "research" / "fast_edge_leaderboard.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=BOT_ROOT / "reports" / "research" / "fast_edge_council_review.json",
    )
    parser.add_argument("--timeout-s", type=int, default=60)
    parser.add_argument("--model", action="append", dest="models", help="limit this run to a configured free model (repeatable)")
    parser.add_argument("--role", action="append", dest="roles", help="limit this run to a council role (repeatable)")
    parser.add_argument("--claude", action="store_true", help="escalate this evidence-triggered review to Claude")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    timeout_s = max(30, int(args.timeout_s))
    swarm = _run_hermes_swarm(
        report,
        timeout_s=timeout_s,
        model_override=args.models,
        role_override=args.roles,
    )
    results = {
        "schema": "fast_edge_council_review.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_report": str(args.report),
        "execution_authority": "NONE",
        "hermes_models_configured": (load_agents_config().get("hermes") or {}).get("models", []),
        "hermes": swarm,
        "hermes_swarm": swarm,
        "claude": None,
    }
    if args.claude:
        # Claude remains a separately requested senior-review path; do not
        # substitute it for the recurring free Hermes research swarm.
        from ai_council.agents import ask_agent
        results["claude"] = ask_agent("claude", _prompt(report, role="SENIOR FALSIFICATION REVIEWER"), timeout_s=timeout_s)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(
        "COUNCIL_RESEARCH_ONLY",
        f"hermes={results['hermes'].get('status')}",
        f"answered={len(results['hermes'].get('models_answered', []))}",
        f"claude={results['claude'].get('status') if results['claude'] else 'NOT_REQUESTED'}",
        f"output={args.output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
