# Task 3 Report: Chronological Basket Replay And Policy Gates

## Files Changed

- `bot/aegis/research/firehose_basket_replay.py`
- `bot/tests/test_firehose_basket_replay.py`
- `task-3-report.md`

## Behavior

Added the research-only `evaluate_basket_policies(rows, policy_packets)` API.
It requires all seven policy families: structural, harvest, extension, floor,
EV, scratch, and combined. It validates complete policy evidence packets,
strictly chronological `TRAIN`, `VALIDATION`, and `OOS`/`SEALED` rows, recorded
costs, normalized risk, capture, turnover, and recorded policy outcomes.

Selection uses costed R expectancy, profit factor, left tail, drawdown, capture,
and turnover, in that order. Win rate is reported but is not a selection gate.
Walk-forward selections only use historical training and prior validation rows;
OOS and sealed rows are never used to select the winner. The result includes an
artifact only after complete selected-policy OOS evidence. The artifact copies
only the packet's normalized R/cost/momentum parameters and has no fixed USD
exit values.

## TDD Evidence

- RED command: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_replay.py -q`
- RED output: collection failed with the expected
  `ModuleNotFoundError: No module named 'aegis.research.firehose_basket_replay'`.
- GREEN command: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_replay.py -q`
- GREEN output: `6 passed in 0.11s`.
- During GREEN, a score-order test exposed floating-point representation noise.
  The comparator now rounds finite score components to 12 decimal places before
  ranking, while retaining the recorded metrics unmodified in output.

## Broader Verification

- `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_replay.py tests\test_firehose_basket_evidence.py tests\test_firehose_basket.py -q`
  completed with `39 passed in 3.07s`.
- Final full-suite command: `..\.venv\Scripts\python.exe -m pytest -q`
  completed with `1067 passed, 1 warning in 82.41s`.
- The one warning is the existing `eventkit` deprecation warning for no current
  event loop in `test_ibkr_order_hygiene.py`.
- `git diff --check` completed without whitespace errors before staging.

## Safety Confirmation

- Missing or malformed evidence, costs, outcomes, partitions, and incomplete
  OOS evidence return `NO_EVIDENCE`; failure results contain no artifact.
- The evaluator consumes caller-provided evidence and observed outcomes only. It
  does not query, fabricate, persist, or promote evidence or metrics.
- No runner, MT5, order, live-trading, configuration, YAML, Research Factory,
  AI Council, Book Brain, or runtime-generated artifact was changed.
- No order was placed and no MT5 or external CLI was launched.

## Self-Review

- Re-read both new files after the focused suite and checked that only the
  planned Task 3 module and tests are in the implementation commit.
- Confirmed the OOS regression gives OOS/sealed data a strongly opposing result
  while retaining the validation winner.
- Confirmed an incomplete selected-policy OOS row returns `NO_EVIDENCE` rather
  than a partial artifact.

## Commits

- Implementation: `40cb234 feat: validate firehose basket policies`

## Concerns

- The checkout contains extensive pre-existing modified and untracked runtime
  artifacts, plus a pre-existing deleted `task-4-report.md`; none were staged,
  changed, or reverted.

## Round 1/5 Fix: Evidence And Walk-Forward Hardening

### Files Changed

- `bot/aegis/research/firehose_basket_replay.py`
- `bot/tests/test_firehose_basket_replay.py`
- `task-3-report.md`

### Behavior

- Every feature is now an observed value with an `available_at` timestamp. A
  missing availability record or one after the row timestamp fails closed; a
  future feature returns `NO_EVIDENCE` with `future_feature_evidence`.
- Every row now requires a complete confirmed lifecycle: basket/ticket identity,
  ordered open/close times, confirmed close, observed MFE/MAE/peak/realized
  values, capture, age, clips, reasons, EV, costs, regime, session, and
  turnover. Missing or malformed lifecycle evidence returns `NO_EVIDENCE`.
- Direct-source packets now require every support and contradiction record to
  retain Task 1 provenance: filename, 64-character file hash/source ID match,
  expected evidence label, nonempty verbatim passage, and indexed path and line
  range. Missing or malformed provenance returns `missing_policy_evidence`.
- Walk-forward decisions now record the selected policy's observed gross PnL,
  cost, risk, costed R return, capture, and turnover. The winner is selected
  from aggregated realized walk-forward outcomes, not the full validation data.

### TDD Evidence

- RED command: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_replay.py -q`
- RED output: `7 failed, 6 passed in 0.25s`. Failures reproduced future feature
  acceptance, missing lifecycle acceptance, incomplete support/contradiction
  provenance acceptance, and full-validation winner selection.
- GREEN focused command: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_replay.py -q`
- GREEN focused output: `13 passed in 0.14s`.

### Broader Verification

- `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_replay.py tests\test_firehose_basket_evidence.py tests\test_firehose_basket.py tests\test_firehose_harvest_research.py tests\test_firehose_harvest_integration.py -q`
  completed with `63 passed in 5.55s`.
- `..\.venv\Scripts\python.exe -m pytest -q` completed with
  `1074 passed, 1 warning in 80.10s`.
- The warning is the pre-existing `eventkit` no-current-event-loop deprecation
  warning in `test_ibkr_order_hygiene.py`.

### Safety And Self-Review

- Missing, malformed, future-dated, or incomplete feature, lifecycle, policy,
  cost, outcome, or OOS evidence returns `NO_EVIDENCE` without an artifact.
- The evaluator remains research-only and does not query, synthesize, persist,
  promote, place orders, start MT5, or enable live trading.
- Re-read the final evaluator and regression tests. Confirmed that OOS data is
  not used for selection, provenance is structurally complete, and the result's
  only policy artifact still carries normalized R/cost/momentum parameters.
- No runner, config, YAML, Research Factory, AI Council, Book Brain, or
  runtime-generated artifact was changed.

### Commit

- `863535a fix: harden firehose basket replay evidence`

### Concerns

- The existing unrelated dirty and runtime-generated worktree artifacts remain
  untouched. The full suite retains the existing single `eventkit` warning.

## Round 2/5 Fix: Source-Content Provenance Verification

### Files Changed

- `bot/aegis/research/firehose_basket_replay.py`
- `bot/tests/test_firehose_basket_replay.py`
- `task-3-report.md`

### Behavior

- The fixed public API remains `evaluate_basket_policies(rows, policy_packets)`.
- Direct evidence records now fail closed unless the declared source path is a
  readable UTF-8 file, its basename equals `filename`, SHA-256 bytes equal the
  recorded `file_hash`/`source_id`, and the cited inclusive line range exactly
  equals the recorded verbatim `passage`.
- This validates the actual source content available in Task 1 packet
  provenance without adding an index or runtime dependency to Task 3. Any
  missing source, unreadable source, digest mismatch, invalid range, or passage
  mismatch returns `NO_EVIDENCE` and no artifact.

### TDD Evidence

- RED command: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_replay.py -q`
- RED output: `1 failed, 13 passed in 0.35s`. The forged 64-character digest
  and matching `source_id` for an otherwise valid declared source incorrectly
  returned `VALIDATED` before the correction.
- GREEN focused command: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_replay.py -q`
- GREEN focused output: `14 passed in 0.29s`.

### Broader Verification

- `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_replay.py tests\test_firehose_basket_evidence.py tests\test_firehose_basket.py -q`
  completed with `47 passed in 3.12s`.
- `..\.venv\Scripts\python.exe -m pytest -q` completed with
  `1075 passed, 1 warning in 78.93s`.
- The warning is the pre-existing `eventkit` no-current-event-loop deprecation
  warning in `test_ibkr_order_hygiene.py`.

### Safety And Self-Review

- The regression uses a real declared source then forges only its digest and
  source ID; the evaluator now rejects it rather than trusting self-asserted
  provenance.
- File reads are limited to caller-declared research evidence paths. No source,
  metric, policy, or artifact is fabricated or persisted, and every source-read
  error fails closed to `NO_EVIDENCE`.
- Re-read the final source and test diff. The implementation is limited to Task
  3, preserves the public interface, and does not change runtime, MT5, orders,
  live trading, configuration, YAML, Research Factory, AI Council, or Book
  Brain code.

### Commit

- `46df116 fix: verify firehose evidence source content`

### Concerns

- Evidence whose indexed source file is unavailable or changed after packet
  creation is intentionally unavailable to Task 3 and fails closed. Unrelated
  worktree artifacts and the existing single `eventkit` warning remain
  untouched.
