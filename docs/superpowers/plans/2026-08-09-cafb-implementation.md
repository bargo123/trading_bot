# CAFB implementation plan

Date: 2026-08-09

1. Add regression tests for historical daily loss, net R, end-of-test liquidation, preparation idempotence, and intraday fallback rejection.
2. Update `RiskEngine`, `run_backtest`, feature preparation, and data fetching until those tests pass without changing unrelated user work.
3. Add tests for failed-break features/signals using synthetic M1 data, including no-look-ahead and cost gating.
4. Implement CAFB features and signal registration with a dedicated config.
5. Add shared-basket tests for chronology, shared equity, portfolio limits, cost-adjusted metrics, currency exposure, and executable lot sizing.
6. Implement a shared basket runner that consumes immutable per-symbol frames and strategy functions.
7. Add a benchmark script that deduplicates aliases, evaluates all existing strategies under the corrected accounting model, tunes CAFB on development/validation only, and opens holdout once.
8. Fetch and snapshot available Yahoo M1/M5 data with exact requested/actual interval metadata. If network or history limits prevent adequate validation, report that boundary and prepare the MT5 path.
9. Run cost and risk stress tests; write `bot/reports/CAFB_BASKET.md` with mandatory metrics and measured conclusions.
10. Run the full direct-test suite, compilation checks, report consistency checks, and `git diff --check`.

