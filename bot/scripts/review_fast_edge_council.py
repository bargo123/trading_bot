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

from ai_council.agents import ask_agent, load_agents_config  # noqa: E402


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


def _prompt(report: dict) -> str:
    model_space = report.get("model_space") or {}
    return (
        "You are a research-only quant council. Do not execute commands, edit files, access MT5, "
        "place orders, change config, or authorize a trade. Analyze the supplied measured shadow evidence.\n\n"
        f"Roles to answer independently then synthesize: {', '.join(ROLES)}.\n"
        "Return JSON with keys: hypotheses (falsifiable, each with required features and rejection gate), "
        "loss_autopsies, exit_recommendations, feature_tests, book_contradictions, and next_experiments. "
        "Reject selection bias, tiny samples, calibration failures, and any result lacking chronological and sealed OOS.\n\n"
        + json.dumps(
            {
                "status": report.get("EXECUTION_STATUS"),
                "rows": report.get("candidate_rows"),
                "symbols": report.get("symbols"),
                "horizons_s": report.get("horizons_s"),
                "top_candidates": report.get("leaderboard_top_50", [])[:12],
                "exit_policy_comparison": report.get("exit_policy_comparison", [])[:12],
                "multi_outcome": report.get("multi_outcome_models"),
                "book_evidence": report.get("book_evidence"),
                "promotion_candidates": model_space.get("promotion_candidates", []),
            },
            indent=2,
            default=str,
        )
    )


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
    parser.add_argument("--timeout-s", type=int, default=240)
    parser.add_argument("--claude", action="store_true", help="escalate this evidence-triggered review to Claude")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    prompt = _prompt(report)
    results = {
        "schema": "fast_edge_council_review.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_report": str(args.report),
        "execution_authority": "NONE",
        "hermes_models_configured": (load_agents_config().get("hermes") or {}).get("models", []),
        "hermes": ask_agent("hermes", prompt, timeout_s=max(30, int(args.timeout_s))),
        "claude": None,
    }
    if args.claude:
        results["claude"] = ask_agent("claude", prompt, timeout_s=max(30, int(args.timeout_s)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(
        "COUNCIL_RESEARCH_ONLY",
        f"hermes={results['hermes'].get('status')}",
        f"claude={results['claude'].get('status') if results['claude'] else 'NOT_REQUESTED'}",
        f"output={args.output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
