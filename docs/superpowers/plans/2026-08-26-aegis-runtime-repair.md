# AEGIS Runtime Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for behavior changes and superpowers:verification-before-completion before claiming success.

**Goal:** Repair the concrete Firehose control-path defects without weakening MT5 DEMO safety or OOS/EV/spread evidence gates, while bounding Codex research work.

**Architecture:** Keep `run_broker_paper.py` as the sole MT5 DEMO execution owner. Keep Research Factory/Watcher/Council read-only. Make fast-exit decisions consume explicit ticket geometry and current calibrated short-horizon support; keep unavailable/shadow evidence fail-closed. Separate generated research evidence from temporary mutation helpers.

**Tech Stack:** Python, pytest, MT5 DEMO runner, AEGIS short-horizon predictor, FastExit state machine.

**Spec:** `docs/superpowers/specs/2026-08-24-firehose-runtime-turnover-design.md`

## Global Constraints

- MT5 DEMO only; `allow_live: false`; never enable real-money execution.
- Exactly one broker execution owner: `bot/scripts/run_broker_paper.py`.
- Council, Factory, Watcher, Book Brain, Claude/Hermes remain read-only to MT5.
- Do not increase per-trade risk or force trades.
- Do not bypass `artifact_shadow_only`, OOS, EV, spread, OMS, or total-drawdown gates.
- `max_daily_loss_percent: 0` is operator-approved for this DEMO environment and must remain unchanged.
- Promotion requires positive chronological TEST and SEALED executable economics with sufficient evidence.

---

### Task 1: Activate the existing rapid-loss scratch contract

**Files:**
- Modify: `bot/aegis/intel/fast_firehose.py`
- Test: `bot/tests/test_fast_exit_production.py`

**Behavior:** `FastExitConfig.min_scratch_loss_frac` already documents “scratch if losing > 30% of stop distance” but is currently unused. Add a pre-timeout downside rule that returns `SCRATCH` with reason `loss_fraction_scratch` when `pnl_pips <= -(min_scratch_loss_frac * R)`. It must not fire when the configured fraction is non-positive.

- [ ] Add a test where stop distance is 10 pips, loss is -3.1 pips, age is below time exit, regime is unchanged, MFE is unarmed; expect `SCRATCH/loss_fraction_scratch`.
- [ ] Add boundary test at -2.9 pips; expect the scratch rule not to fire.
- [ ] Run the targeted test and confirm RED before implementation.
- [ ] Implement the minimal rule after regime invalidation and before time decay.
- [ ] Re-run targeted tests and confirm GREEN.

### Task 2: Revoke losing trades when calibrated short-horizon support disappears

**Files:**
- Modify: `bot/aegis/intel/fast_exit_runner.py`
- Modify: `bot/scripts/run_broker_paper.py`
- Test: `bot/tests/test_fast_exit_production.py`

**Behavior:** The existing runner labels a geometry-scaled copy of entry EV as `ESTIMATED`, even though it is not a point-in-time model estimate. Change the geometry fallback status to `PROXY`. Add optional current short-horizon prediction evidence to `FastExitContext`. A calibrated, non-abstaining prediction that no longer authorizes the ticket side may abort a non-profitable position with reason `short_horizon_support_revoked`. Shadow-only/unavailable/abstaining predictions must not masquerade as current evidence.

- [ ] Add tests proving calibrated negative current support aborts a losing ticket.
- [ ] Add tests proving shadow-only/abstaining/unavailable support does not create an executable model-revocation exit.
- [ ] Add tests proving a profitable ticket remains governed by target/MFE/harvest rules rather than being converted into a model-revocation loss exit.
- [ ] Run tests RED.
- [ ] Implement the minimal context fields and rule.
- [ ] In runner, recompute prediction for the open ticket side from the existing `ShortHorizonPredictor` and `QuoteBuffer`; keep the geometry fallback explicitly `PROXY`, not `ESTIMATED`.
- [ ] Run focused tests GREEN.

### Task 3: Clean temporary mutation helpers without deleting governed evidence

**Files:**
- Delete untracked one-off helpers only: `_temp_check.py`, `bot/add_calculate_metrics.py`, `bot/add_calculate_metrics2.py`, `bot/add_method.py`, `bot/add_research_cycle.py`, `bot/add_test_method.py`, `bot/fix_add_method.py`, `bot/fix_final.py`, `bot/fix_hypothesis.py`, `bot/fix_hypothesis_dataclass.py`, `bot/fix_hypothesis_gen.py`, `bot/fix_hypothesis_v2.py`, `bot/fix_imports.py`, `bot/fix_method3.py`, `bot/fix_return.py`, `bot/fix_syntax.py`, `bot/fix_syntax_final.py`, `bot/fix_test.py`, `bot/fix_test2.py`.

**Behavior:** Do not delete Factory/Council cases, experiment SQLite, leaderboards, lifecycle evidence, generated model artifacts, or `.ai-bridge` coordination files.

- [ ] Confirm each listed helper is a one-off mutation/debug script and not imported by production/tests.
- [ ] Delete only those helpers.
- [ ] Leave `task-4-report.md` deletion untouched until its intent is reviewed.

### Task 4: Bound research and validate the two watcher survivors

**Files:**
- Coordination: `.ai-bridge/current-plan.md`
- Evidence only under `bot/reports/research/` and `bot/research/`.

**Behavior:** The no-trade blocker is evidence, not connectivity: current artifact is `SHADOW_ONLY_NO_POSITIVE_OOS`. Do not bypass it. Trace the exact two watcher-surviving strategy IDs through the same strict executable short-horizon TEST/SEALED/cost pipeline.

- [ ] Stop the Codex batch after both survivors are evaluated, or 3 materially different full replays, or 75 minutes, whichever comes first.
- [ ] Promote nothing unless TEST and SEALED expectancy are positive after costs, PF > 1, sample/loss evidence is sufficient, and tail behavior is acceptable.
- [ ] If both fail, test at most one materially different mechanism aimed at the measured failure cause, then idle.
- [ ] Do not create new `fix_*.py` / `add_*.py` helper scripts.

### Verification

Run from `bot`:

`..\.venv\Scripts\python.exe -m pytest tests/test_fast_exit_production.py tests/test_short_horizon_runtime.py tests/test_run_broker_paper_helpers.py -q`

Then full suite:

`..\.venv\Scripts\python.exe -m pytest -q`

Before claiming completion, report exact pass/fail counts, runner heartbeat freshness, model execution status, authorized symbols, SCANS/MICRO_CANDIDATES/ML_ELIGIBLE/FIRES/FILLS, and any remaining blocker.
