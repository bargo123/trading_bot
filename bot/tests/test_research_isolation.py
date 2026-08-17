from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_paper_runner_does_not_import_research():
    source = (ROOT / "scripts" / "run_broker_paper.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert all("research" not in name.split(".") for name in imported)
    assert "aegis.research" not in source
    assert "aegis.portfolio_risk" not in source
    assert "aegis.reconcile" not in source
    assert "thesis_fire" not in source
    assert "evaluate_thesis_fire" not in source


def test_shadow_script_is_readonly_and_uses_own_lock():
    source = (ROOT / "scripts" / "research_firehose_shadow.py").read_text(encoding="utf-8")
    assert "place_order" not in source
    assert "mt5.shutdown" not in source
    assert "disconnect(shutdown=True)" not in source
    assert "research_firehose_shadow.lock" in source
    assert "run_broker_paper.lock" not in source
    assert "placed_orders" in source
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert any(name == "aegis.research.shadow_observe" or name.startswith("aegis.research") for name in imported)
