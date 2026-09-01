from __future__ import annotations

from pathlib import Path

from aegis.research.external_dag.catalog import load_external_catalog


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TOOLS = {
    "OpenAlice",
    "awesome-systematic-trading",
    "qlib",
    "ordersim",
    "hftbacktest",
    "oos-lab",
    "Keystone",
    "algorithmic-trading-research-framework",
    "samvid-trading-core",
    "Vibe-Trading",
    "metatrader5-mcp-server",
    "nautilus_trader",
    "Lean",
    "abides",
}


def test_catalog_matches_every_installed_repository_and_preserves_sha():
    catalog = load_external_catalog(PROJECT_ROOT)

    assert {tool.tool_id for tool in catalog} == EXPECTED_TOOLS
    assert len(catalog) == 14
    assert all(len(tool.repository_sha) == 40 for tool in catalog)
    assert all(Path(tool.repository_path).is_dir() for tool in catalog)
    assert all(tool.capabilities and tool.command for tool in catalog)
    assert all(tool.broker_authority is False for tool in catalog)


def test_catalog_rejects_manifest_missing_a_required_tool(tmp_path):
    report = tmp_path / "bot" / "reports" / "research"
    report.mkdir(parents=True)
    (report / "external_dependency_manifest.json").write_text(
        '{"repositories":[{"name":"qlib","commit":"' + "a" * 40 + '"}]}',
        encoding="utf-8",
    )

    try:
        load_external_catalog(tmp_path)
    except ValueError as exc:
        assert "missing required external tools" in str(exc)
    else:
        raise AssertionError("an incomplete external catalog was accepted")
