# Firehose Basket Evidence Final Fix Report

## Scope

This final-review fix wave addresses only the three controller rulings recorded
in `progress.md`. It changes the Firehose DEMO exploration switch, the
research-only basket replay admission path, and focused regressions. No runner,
order path, MT5 session, live-trading setting, Research Factory, AI Council,
Book Brain, or unrelated dirty artifact was changed.

## Findings And Fixes

### DEMO Exploration Safety

`bot/config_mt5_demo_firehose_hw.yaml` now sets
`intelligent_exploration_enabled: false`. The YAML change is limited to that
single value. `allow_live: false` and
`exploration_max_risk_per_trade_usd: 0.15` are preserved exactly. The paper
control regression loads the actual configuration and asserts all three values.

### OOS Artifact Admission

The replay evaluator retains its existing trusted-provenance, chronology,
cost, feature, lifecycle, policy-outcome, and selected-policy OOS-completeness
checks. After those checks, it computes the selected policy's costed OOS
metrics and calls the artifact admission gate.

The applicable basket-replay contract has no governed threshold that defines
acceptable expectancy, profit factor, tail, and drawdown together. Existing
canary and strategy-model thresholds govern different artifacts and do not
provide a basket OOS drawdown criterion. The evaluator consequently returns
`NO_EVIDENCE` with `missing_governed_oos_policy_gate`; it does not invent
thresholds or emit a `VALIDATED` artifact. A regression covers complete,
positive, costed direct-source OOS evidence and verifies this no-artifact
result.

### Novel Hypotheses

After the existing packet validator accepts a structurally valid packet,
`NOVEL_SYNTHESIZED_HYPOTHESIS` origins now return `NO_EVIDENCE` with
`missing_stronger_novel_empirical_gate`. No stronger governed empirical gate
exists, so novel packets cannot emit artifacts. This decision occurs after
packet validation, preserving direct-source trusted provenance behavior. The
regression also confirms a novel-only packet does not need BookIndex access to
reach its controlled no-evidence result.

## Regression Preservation

The prior successful-artifact assertions were converted to no-evidence
expectations because this controller ruling intentionally removes the former
success path until governance is supplied. The following protections remain
and pass in the replay suite: strict chronology, future-feature rejection,
complete confirmed lifecycle, recorded costs, trusted indexed provenance,
malformed path failure closure, OOS/sealed non-selection, incomplete OOS
rejection, and no-artifact behavior.

## TDD Evidence

The new replay regressions and configuration assertion were run before the
production changes. They failed as expected:

- `test_rejects_novel_only_packets_even_when_the_book_index_is_unavailable`
  observed a `VALIDATED` result.
- `test_rejects_complete_positive_direct_source_oos_without_a_governed_policy_gate`
  observed a `VALIDATED` result.
- `test_mt5_firehose_hw_is_demo_gated_shape` observed
  `intelligent_exploration_enabled is True`.

## Verification

- Focused: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_firehose_basket_replay.py tests\\test_firehose_basket_evidence.py tests\\test_firehose_basket.py tests\\test_firehose_basket_runtime.py tests\\test_paper_control.py -q`
  passed: `75 passed in 4.66s`.
- Full: `..\\.venv\\Scripts\\python.exe -m pytest -q` passed:
  `1086 passed, 1 warning in 95.96s`.
- `git diff --check` reported no whitespace errors. Git reported only existing
  LF-to-CRLF conversion warnings for touched files and the unrelated dirty
  `research_factory/core.py` file.

## Self-Review

Reviewed the exact implementation diff and confirmed:

- The only YAML value changed is the controller-specified exploration flag.
- Novel gating occurs only after packet structural validation, so direct-source
  provenance verification is unchanged.
- The OOS no-evidence outcome follows all existing evidence completeness checks
  and has no `artifact` field.
- No threshold was fabricated or borrowed across incompatible governance
  contracts.
- Unrelated dirty and generated artifacts were neither modified nor staged by
  this wave.

## Residual Concern

All basket policy artifacts remain intentionally unavailable until a separately
governed basket OOS gate defines acceptable costed expectancy, profit factor,
tail, and drawdown criteria. The full suite retains the existing `eventkit`
deprecation warning about no current event loop.
