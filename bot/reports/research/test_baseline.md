# Test baseline — 2026-08-17

Full suite after Phase 1 inventory, Phase 2 collection repair, and two-level firehose gates.

Command: `python -m pytest -q` from `bot/` using `.venv`.

## Collection

**433 tests collected.** Previous audit could not collect the full suite because `collect_order_rows` and `child_specs` were missing. Those APIs were restored from the Codex worktree copies of `run_dashboard.py` and `watchdog.py`. The watchdog restart loop was not pointed at the live MT5 firehose.

## Result

**428 passed, 5 failed, 1 warning.**

## Failures (pre-existing; not hidden)

| Test | Class | Why |
|---|---|---|
| `test_ib_paper_config_defaults_to_observation_only` | pre-existing config drift | `config_ib_paper_eurusd.yaml` lacks `paper_trading_enabled` and is not observation-only. **Not** the live MT5 firehose YAML; left untouched. |
| `test_generic_strategy_router_prepares_hale_for_paper_runner` | pre-existing | `KeyError: donchian_period` in `indicators.py` during HALE prepare. Unrelated to firehose intelligence. |
| `test_start_service_preserves_virtualenv_python_launcher_path` | pre-existing on Windows | `os.getuid` does not exist; launchd helper is macOS-only. |
| `test_stop_quiesces_supervisor_before_flattening` | pre-existing on Windows | same `os.getuid` / launchd. |
| `test_stop_waits_for_launchd_job_to_finish_unloading` | pre-existing on Windows | same `os.getuid` / launchd. |

## New tests in this slice

- `tests/test_intel_expected_value.py`
- `tests/test_intel_thesis_fire.py`
- payoff/structural gates in `tests/test_research_govern.py`
- shadow cycle fire-decision assertions in `tests/test_research_intelligence.py`

## Not done in this slice

- Live YAML / runner / CORE `sig_firehose` unchanged
- Intelligent firehose not connected to `intel/decide.py` or MT5
- Codex `portfolio_risk.py` / `reconcile.py` not merged
- Disabled live DD limits still CRITICAL and unresolved
