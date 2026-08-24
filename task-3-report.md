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
