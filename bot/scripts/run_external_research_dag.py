"""Run or inspect the bounded, read-only external research DAG."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Sequence

BOT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BOT_ROOT.parent
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))

from aegis.research.external_dag.adapters import build_adapter_registry
from aegis.research.external_dag.catalog import REQUIRED_EXTERNAL_TOOLS
from aegis.research.external_dag.orchestrator import (
    WORKFLOW_ID,
    build_full_research_workflow,
    execute_research_workflow,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AEGIS external research DAG")
    parser.add_argument("--workflow", default=WORKFLOW_ID, choices=[WORKFLOW_ID])
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument(
        "--artifact-root",
        default=str(BOT_ROOT / "research" / "external_dag" / "artifacts"),
    )
    parser.add_argument(
        "--registry", default=str(BOT_ROOT / "research" / "experiments.sqlite")
    )
    parser.add_argument(
        "--status-path",
        default=str(BOT_ROOT / "reports" / "research" / "external_dag_status.json"),
    )
    parser.add_argument(
        "--execution-bundle-path",
        default=str(BOT_ROOT / "intel" / "execution_bundle.json"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    workflow = build_full_research_workflow()
    catalog = build_adapter_registry(PROJECT_ROOT, timeout_s=args.timeout_s)
    if args.dry_run:
        nodes = []
        for node in workflow.nodes:
            adapter = catalog.get(node.adapter)
            spec = getattr(adapter, "spec", None)
            nodes.append(
                {
                    "node_id": node.node_id,
                    "tool_id": node.tool_id,
                    "adapter": node.adapter,
                    "dependencies": list(node.dependencies),
                    "command": list(spec.command) if spec is not None else [],
                    "environment": spec.environment if spec is not None else "internal",
                    "broker_authority": False,
                    "timeout_s": spec.timeout_s if spec is not None else args.timeout_s,
                }
            )
        print(
            json.dumps(
                {
                    "workflow_id": workflow.workflow_id,
                    "external_tools": sorted(REQUIRED_EXTERNAL_TOOLS),
                    "book_algorithm_node": "aegis-book-algorithms",
                    "nodes": nodes,
                    "artifact_root": str(Path(args.artifact_root)),
                    "registry": str(Path(args.registry)),
                    "status_path": str(Path(args.status_path)),
                    "execution_bundle_path": str(Path(args.execution_bundle_path)),
                    "starts_processes": False,
                },
                sort_keys=True,
            )
        )
        return 0

    run_id = args.run_id or datetime.now(timezone.utc).strftime("external-%Y%m%dT%H%M%SZ")
    outcome = execute_research_workflow(
        project_root=PROJECT_ROOT,
        dataset_manifest_path=Path(args.dataset_manifest),
        run_id=run_id,
        artifact_root=Path(args.artifact_root),
        registry_path=Path(args.registry),
        status_path=Path(args.status_path),
        execution_bundle_path=Path(args.execution_bundle_path),
        max_workers=args.max_workers,
        timeout_s=args.timeout_s,
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "complete": outcome.research_bundle.complete,
                "research_bundle_hash": outcome.research_bundle.bundle_hash,
                "promotion_status": outcome.promotion.status,
                "promotion_reasons": list(outcome.promotion.reasons),
                "execution_bundle_hash": (
                    outcome.execution_bundle.bundle_hash
                    if outcome.execution_bundle is not None else None
                ),
            },
            sort_keys=True,
        )
    )
    return 0 if outcome.research_bundle.complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
