"""Continuously refresh the read-only universal fast-edge shadow generation."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


BOT_ROOT = Path(__file__).resolve().parents[1]
WORKER = Path(__file__).resolve().with_name("research_fast_edge_shadow.py")
EXPERIMENT_HANDOFF = "fast_edge_experiment_handoff.json"


def _compact_proposal(value):
    if isinstance(value, dict):
        compact = {}
        for key, item in value.items():
            if isinstance(item, str) and len(item) > 2000:
                continue
            compact[key] = _compact_proposal(item)
        return compact
    if isinstance(value, list):
        return [_compact_proposal(item) for item in value[:50]]
    return value


def _collect_named_items(value, name: str) -> list[dict]:
    found: list[dict] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == name and isinstance(item, list):
                found.extend(item for item in item if isinstance(item, dict))
            else:
                found.extend(_collect_named_items(item, name))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_named_items(item, name))
    unique = []
    seen = set()
    for item in found:
        compact = _compact_proposal(item)
        marker = json.dumps(compact, sort_keys=True, default=str)
        if marker not in seen:
            seen.add(marker)
            unique.append(compact)
    return unique[:100]


def _extract_experiment_handoff(review: dict) -> dict:
    hermes = review.get("hermes") or {}
    claude = review.get("claude") or {}
    return {
        "schema": "fast_edge_experiment_handoff.v1",
        "source_schema": review.get("schema"),
        "generated_at": review.get("generated_at"),
        "source_report": review.get("source_report"),
        "execution_authority": "NONE",
        "next_experiments": _collect_named_items(hermes, "next_experiments"),
        "hypotheses": _collect_named_items(hermes, "hypotheses"),
        "feature_tests": _collect_named_items(hermes, "feature_tests"),
        "exit_recommendations": _collect_named_items(hermes, "exit_recommendations"),
        "claude_next_experiments": _collect_named_items(claude, "next_experiments"),
    }


def _write_experiment_handoff(destination: Path, handoff: dict) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(handoff, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=BOT_ROOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--out-dir", type=Path, default=BOT_ROOT / "reports" / "research")
    parser.add_argument("--lookback-seconds", type=int, default=3600)
    parser.add_argument("--sample-every-seconds", type=int, default=5)
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--council", action="store_true", help="run the bounded research-only Council handoff after each generation")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    while True:
        generation = args.out_dir / "fast_edge_generations" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        generation.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable, str(WORKER),
            "--config", str(args.config),
            "--out-dir", str(generation),
            "--lookback-seconds", str(max(60, int(args.lookback_seconds))),
            "--sample-every-seconds", str(max(1, int(args.sample_every_seconds))),
            "--no-rows",
        ]
        prior_handoff = args.out_dir / EXPERIMENT_HANDOFF
        if prior_handoff.exists():
            command.extend(["--experiment-handoff", str(prior_handoff)])
        result = subprocess.run(command, cwd=str(BOT_ROOT.parent), check=False)
        latest = generation / "fast_edge_leaderboard.json"
        if result.returncode == 0 and latest.exists():
            shutil.copy2(latest, args.out_dir / "fast_edge_leaderboard.json")
            handoff = generation / "fast_edge_factory_handoff.json"
            if handoff.exists():
                shutil.copy2(handoff, args.out_dir / "fast_edge_factory_handoff.json")
            if args.council:
                council_output = generation / "fast_edge_council_review.json"
                subprocess.run(
                    [
                        sys.executable,
                        str(BOT_ROOT / "scripts" / "review_fast_edge_council.py"),
                        "--report", str(latest),
                        "--output", str(council_output),
                    ],
                    cwd=str(BOT_ROOT.parent), check=False,
                )
                if council_output.exists():
                    try:
                        review = json.loads(council_output.read_text(encoding="utf-8"))
                        _write_experiment_handoff(
                            args.out_dir / EXPERIMENT_HANDOFF,
                            _extract_experiment_handoff(review),
                        )
                        _write_experiment_handoff(
                            generation / EXPERIMENT_HANDOFF,
                            _extract_experiment_handoff(review),
                        )
                    except (OSError, json.JSONDecodeError, TypeError, ValueError):
                        pass
        if args.once:
            return int(result.returncode)
        time.sleep(max(60, int(args.interval_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
