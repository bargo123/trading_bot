from __future__ import annotations

from types import SimpleNamespace

import aegis.research.watcher_algorithms as watcher_algorithms


def _result(name: str) -> dict[str, object]:
    return {
        "algorithm_id": name,
        "view": "WAIT",
        "applicability": "APPLICABLE",
        "reasons": [],
        "inputs_used": [],
        "missing_inputs": [],
        "source_books": [],
        "execution_authority": False,
        "uses_future_data": False,
        "research_only": True,
        "no_lookahead": True,
    }


def test_bulk_evaluation_caches_algorithm_module_resolution(monkeypatch):
    names = ("first", "second")
    modules = {
        name: SimpleNamespace(evaluate=lambda state, name=name: _result(name), SOURCES=())
        for name in names
    }
    calls: list[str] = []

    monkeypatch.setattr(watcher_algorithms, "ALGORITHM_MODULES", names)
    monkeypatch.setattr(
        watcher_algorithms,
        "import_module",
        lambda module_name: calls.append(module_name) or modules[module_name.rsplit(".", 1)[-1]],
    )
    watcher_algorithms._loaded_algorithm_modules.cache_clear()

    first = watcher_algorithms.evaluate_all({})
    second = watcher_algorithms.evaluate_all({})

    assert [row["algorithm_id"] for row in first] == list(names)
    assert [row["algorithm_id"] for row in second] == list(names)
    assert calls == [f"{watcher_algorithms.__name__}.{name}" for name in names]
    watcher_algorithms._loaded_algorithm_modules.cache_clear()
