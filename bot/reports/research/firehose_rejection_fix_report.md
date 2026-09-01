# Firehose integration verification

The verified source path is the existing governed execution owner,
`bot/scripts/run_broker_paper.py`. No second sender was added and
`MT5Engine.place_order()` remains the only engine path to `mt5.order_send()`.

The Watcher advisory is permanently research-only. It may contribute causal,
book-attributed ranking evidence, but it carries
`execution_authority=false`, `research_only=true`, and `order_intent=false`.

The runner now admits normalized broker timestamps rather than treating the
MT5 server's +03:00 wall clock as UTC. An earlier captured post-restart
runtime interval recorded 19 causal events accepted and 33 quarantined with a
healthy feed; the previous all-`future_event` ledger failure is therefore
fixed. The current runner is stopped while promotion evidence is incomplete.

The corrected shadow replay now records a per-row cost-model contract
(`aegis.shadow_cost_model.v1`) and excludes its fixed slippage, commission,
latency, and USD-conversion metadata from the predictive feature matrix. These
values remain audit evidence; they cannot become accidental training inputs.

The unsafe uncalibrated forced-order lane is retired. Governed DEMO exploration
may remain below the 95% optimization target, but it still requires measured
point-in-time probability and positive executable economics. The current model
is `SHADOW_ONLY_NO_POSITIVE_OOS`; consequently no signal was forced and runtime
reports `short_horizon_not_calibrated`.

Verification: the current isolated full suite is `3263 passed, 108 warnings,
0 failures`; the focused rapid-benchmark and external-DAG regression set is
`10 passed, 0 failures`; Firehose verifier reports `38 VERIFIED`. The
genuine-artifact validation tightening described below is included in those
checks.
The optional verifier `--runtime` liveness probe remains
unavailable on this Windows host because its `tasklist` subprocess times out;
direct process inspection confirms the recorded runner PID is stopped.

## Exact book-derived rejection funnel audit (2026-09-01)

The stopped-run checkpoint in `bot/reports/bot_heartbeat.json` at
`2026-09-01T17:59:19.778564Z` (local `20:59:19.778564+03:00`) recorded 12
book-derived mechanisms loaded and tested, 12,696 book-derived candidates,
and 0 selected (0% selection). This is an intentional fail-closed result,
not missing candidate generation. The observed counters were: spread failures
2,019; geometry/tail failures 213; risk failures 12,418; net-EV/probability
failures 2,539; multi-gate failures 1,952; near-eligible variants 438; and
`BEST_REJECTED_REASON=RISK_GRANULARITY_BLOCKED`. The same checkpoint had
`EXPLORATION_ELIGIBLE=0`, `FIRES=0`, and `FILLS=0`; the short-horizon artifact
was `SHADOW_ONLY_NO_POSITIVE_OOS`. The heartbeat is evidence from that stopped
interval, not proof that a runner remains active.

The checkpoint's skip-reason distribution was: `short_horizon_not_calibrated`
1,665; `exploration_economics_rejected:RISK_GRANULARITY_BLOCKED` 732;
`no_micro_candidate_matched` 526; `spread_above_measured_session_limit` 337;
`exploration_economics_rejected:no_win_probability_evidence` 314;
`...:INVALID_GEOMETRY` 65; `...:SPREAD_FAILURE` 20;
`...:NEGATIVE_EXPECTED_NET_AFTER_COST` 6; and
`...:invalidation_not_above_entry` 2.

Every generated candidate is evaluated in this order:

1. **Contract value and entry economics.** Use the conservative positive
   broker `tick_value/tick_size` pair (loss, total, and profit values are
   normalized to positive magnitudes); fall back to a finite positive contract
   size only when the pair is unavailable. Reject unavailable/non-finite
   contract value. At minimum lot, `min_lot_risk = abs(entry-invalidation) *
   USD_per_price_unit_per_lot * volume_min` must not exceed the configured risk
   budget. Cost in pips is `spread + slippage + commission /
   (USD_per_price_unit_per_lot * pip * volume_min)`; net target must remain
   positive. Spread is capped at half the target, stop geometry is bounded to
   0.5--20 pips, and measured p90 spread remains a separate gate.
2. **Risk conversion and minimum lot.** Final sizing uses the same broker-native
   conversion, rounds down to `volume_step`, and refuses a minimum lot or step
   that breaches the budget. This is why the leading rejection is
   `RISK_GRANULARITY_BLOCKED`; the lot is not rounded up to manufacture an
   order.
3. **Portfolio/OMS gate.** The sized candidate must fit position, symbol, and
   currency-direction limits before economics are scored.
4. **Exact trade economics.** Structural reward/risk are converted with
   `USD_per_price_unit = tick_value / tick_size * lots` (or the finite contract
   fallback). `expected_win = reward_price * USD_per_price_unit`,
   `expected_loss = risk_price * USD_per_price_unit`, and
   `cost = (spread_price + slippage_price) * USD_per_price_unit + fixed
   round-trip commission`. `E = p_win*expected_win - (1-p_win)*expected_loss -
   cost`; payoff must meet the configured 1R floor and E must be strictly
   positive.
5. **Measured probability/capture and memory.** A probability is accepted only
   from executable captured-market evidence; otherwise the candidate is
   rejected. Analogue evidence uses the Wilson lower bound, and capture
   authorization requires its lower bound to clear the geometry-derived
   breakeven rate with the minimum observation count. Fast-loser memory and the
   final payoff/spread checks remain vetoes.
6. **Selection.** `BOOK_DERIVED_SELECTED` increments only after every preceding
   gate. Since no candidate reached that point, zero is the correct result.

Calculation corrections applied during this audit: final exploration sizing now
uses the same conservative `max(abs(loss_tick_value), abs(generic_tick_value),
abs(profit_tick_value)) / tick_size` conversion as preview sizing; non-finite or
negative spread/slippage/commission inputs fail closed instead of becoming zero;
and invalid risk/geometry/volume inputs (including a minimum lot not aligned to
the broker step) are rejected before any lot is produced. The legacy
`check_entry_economics` path now applies the same finite-positive budget and
volume checks and rejects malformed/negative commission or slippage before
arithmetic. `evaluate_trade_economics` now also rejects non-finite position
sizes, economic thresholds, broker conversions, and derived USD calculations
before payoff or expected-value comparisons. Exit/money conversion now also
chooses the largest finite broker profit/loss tick value when MT5 reports
side-specific values. These changes tighten the funnel and do not alter its
safety thresholds.

Two replay-accounting defects were proven with regression tests and fixed.
`build_shadow_dataset` now charges configured `slippage_bps` as round-trip
slippage (`2 * mid * bps / 10000`), matching the governed runner and short-
horizon artifact; the old path charged one side. `TradeController` now keeps
every executable quote observed during a delayed close in the realized path,
so captured PnL is represented by the same MFE/MAE and peak-time series.
Across the rebuilt rows, `captured_exit_net_pnl > mfe_net_pnl` occurred 0 times
and `mae_net_pnl > captured_exit_net_pnl` occurred 0 times.

### Current authoritative cost-aware replay (2026-09-01)

The focused rebuild replayed 34,923 rows through the reconstructed causal
prior-history path for exactly the same nine measurable algorithms (not the
616-entry registry). Every row has a net outcome and the complete per-row
cost contract `aegis.shadow_cost_model.v1`: executable bid/ask spread,
0.1 bps slippage, 0 round-trip commission, 0.2 s entry latency, 0.2 s close
latency, and USD-per-price-unit conversion. The row-file SHA-256 is
`d8cab24eb3a8b789cd2f2d4bc0009192ab87a1a5d3e639f6f2c52175ff1fb6f8`; the
replay report SHA-256 is
`aa229a07fd53d64cdaef837044cbb176ff76961d3f96aa3714b2b41ed212206e`.
Chronological ranges are train `[0,19000)`, validation `[19005,24000)`, test
`[24005,29000)`, and sealed `[29005,34923)`, with a five-row purge. All nine
aggregate algorithms are negative after the runner-wide rejection adjustment:

| selected algorithm | signals | rejection-adjusted expectancy | PF |
|---|---:|---:|---:|
| `bollinger_bands` | 8,448 | -0.00002203 | 0.126 |
| `breakout_quality` | 9,183 | -0.00002446 | 0.112 |
| `donchian_breakout` | 11,539 | -0.00002355 | 0.116 |
| `breakout_continuation` | 11,525 | -0.00002351 | 0.116 |
| `rsi_reversal` | 5,152 | -0.00002440 | 0.090 |
| `oscillator_signal` | 5,152 | -0.00002440 | 0.090 |
| `divergence` | 4,621 | -0.00002366 | 0.095 |
| `williams_reversal` | 10,854 | -0.00002436 | 0.088 |
| `support_resistance` | 10,609 | -0.00002345 | 0.117 |

Exact identity eligibility (`signal_samples >= 20`, losses >= 5) produced
476 train, 149 validation, 182 test, and 268 sealed identities; zero were
positive in any split, and the validation/sealed positive intersection is
zero. This is the authoritative cost-aware result for promotion. It does not
authorize an execution bundle.

A fresh bounded expansion (`watcher_replay_87039e141e746522_10000`) used
exactly the same 9 selected algorithms (not the 616-entry registry), replayed
10,000 rows with four chronological splits and a five-row purge, and attached
outcomes to all 10,000 rows. Its input-row hash is
`87039e141e7465220123ae25bc2b0df4d82fe8c05b9335f1d7818383d319d92b` and its
replay-report hash is `bc665bf10780ab8cee567828c9bd17661191b42e579dbd918e7877a30414ede0`.
The legacy frozen row file does not carry explicit entry/close-latency,
slippage, or commission metadata, so this expansion is diagnostic and cannot
replace the corrected cost-aware replay for promotion. The runner-wide
rejection adjustment was `165/(849+165)=0.1627218935`; it is explicitly
runner-wide, not strategy-specific, applied to expectancy only, and does not
change rejection classification.

| selected algorithm | signals | win rate | expectancy | rejection-adjusted expectancy |
|---|---:|---:|---:|---:|
| `bollinger_bands` | 30 | 13.3333% | -0.00002957 | -0.00002476 |
| `breakout_quality` | 142 | 9.8592% | -0.00001745 | -0.00001461 |
| `donchian_breakout` | 182 | 7.6923% | -0.00001941 | -0.00001625 |
| `breakout_continuation` | 172 | 8.1395% | -0.00001799 | -0.00001506 |
| `rsi_reversal` | 1,932 | 13.8716% | -0.00003297 | -0.00002761 |
| `oscillator_signal` | 1,932 | 13.8716% | -0.00003297 | -0.00002761 |
| `divergence` | 777 | 8.4942% | -0.00003357 | -0.00002810 |
| `williams_reversal` | 917 | 12.5409% | -0.00002876 | -0.00002408 |
| `support_resistance` | 68 | 11.7647% | -0.00001766 | -0.00001479 |

The 10k split ranges were train `[0,5500)`, validation `[5505,7000)`, test
`[7005,8500)`, and sealed `[8505,10000)`. Exact identity replay covered 4,662
identities in both forward OOS splits; zero identities were positive in both
validation and sealed after the rejection adjustment with at least 20 signals
and 5 losses. `no_lookahead=true` and outcomes were attached only after each
causal evaluation. The separately rebuilt 1,950-row quote replay was the
earlier authoritative full-cost check (explicit executable spread, 0.1 bps
round-trip slippage, 0 commission, and 0.2 s entry/close latency) and likewise
had zero positive exact identities; the larger 34,923-row replay above
supersedes it as the current focused result.

A supplemental 100,000-row run of the same nine IDs used the reconstructed
prior-history feature path with universe context omitted and same-quote context
reuse enabled. This optimization was regression-compared with ordinary replay
on 2,000 rows and produced identical selected decisions and exact metrics. All
nine aggregate algorithms remained negative in train, validation, test, and
sealed; the forward split rejection-adjusted expectancy/PF pairs were:

| selected algorithm | validation rejection-adjusted expectancy / PF (n) | sealed rejection-adjusted expectancy / PF (n) |
|---|---:|---:|
| `bollinger_bands` | -0.00002063 / 0.079 (1,991) | -0.00002953 / 0.061 (2,030) |
| `breakout_quality` | -0.00002545 / 0.050 (3,076) | -0.00003019 / 0.065 (2,171) |
| `donchian_breakout` | -0.00002580 / 0.048 (3,423) | -0.00003025 / 0.063 (2,231) |
| `breakout_continuation` | -0.00002580 / 0.048 (3,423) | -0.00003025 / 0.063 (2,231) |
| `rsi_reversal` | -0.00002117 / 0.067 (1,243) | -0.00003048 / 0.093 (2,710) |
| `oscillator_signal` | -0.00002117 / 0.067 (1,243) | -0.00003048 / 0.093 (2,710) |
| `divergence` | -0.00002793 / 0.046 (1,929) | -0.00002530 / 0.146 (1,542) |
| `williams_reversal` | -0.00002570 / 0.058 (4,064) | -0.00002827 / 0.100 (5,127) |
| `support_resistance` | -0.00002665 / 0.050 (3,089) | -0.00002965 / 0.070 (1,753) |

The frozen legacy rows do not carry a complete per-row cost-model manifest, so
this 100k expansion is corroborating diagnostic evidence only. It cannot
replace the current explicit-cost 34,923-row replay or authorize an execution
bundle.
Promotion now also requires `cost_model_provenance` with `status=COMPLETE`,
`per_row=true`, matching checked/complete row counts, executable spread,
slippage, commission, latency, and USD conversion fields. The legacy selected
replay fails closed on this gate (`selected_strategy_cost_model_missing`); its
`cost` column is not treated as proof of the underlying assumptions.

A separate recent-window check replayed all 48,498 rows captured on
2026-08-31 (`live_github_books_20260831/fast_edge_shadow_rows.jsonl`,
SHA-256 `37f429f4815b130b9e2f9ce2a134d700b04735743840bfd6f2137f78f19ef843`).
It used the same nine IDs, reconstructed prior-history features, omitted
universe context, and reused same-quote context; the run took 549.525 seconds.
The aggregate rejection-adjusted expectancy/PF results were negative for all
nine IDs (`bollinger_bands` -0.00000316/0.492,
`breakout_quality` -0.00000228/0.569, `donchian_breakout` and
`breakout_continuation` -0.00000330/0.470, `rsi_reversal` and
`oscillator_signal` -0.00000397/0.433, `divergence` -0.00000238/0.600,
`williams_reversal` -0.00000277/0.545, and `support_resistance`
-0.00000336/0.469). The forward splits also stayed negative wherever signals
were present: validation values ranged from -0.00000177 to -0.00000449,
test from -0.00000129 to -0.00000372, and sealed from -0.00000188 to
-0.00000333. Sixteen exact identities cleared the diagnostic validation
threshold and two cleared sealed, but their intersection was zero. Because
these captured rows still lack a complete per-row spread/slippage/commission/
latency manifest, this is corroboration only and does not alter the
authoritative explicit-cost result or authorize a bundle.

## Selected-strategy external artifact audit

The fresh bounded external run (`github-books-watcher-costaware-20260901T185609Z`)
used exactly the same 9 selected IDs (not the full registry). Verified
content-addressed domain artifacts exist for Qlib
(`trained_offline_model_and_features`), ordersim (`candidate_execution_replay`),
hftbacktest (`candidate_tick_execution_replay`), OOS-Lab
(`calculated_statistical_validation`), Keystone
(`calculated_methodology_validation`), Nautilus
(`replay_parity_comparison`), ABIDES (`latency_and_failure_stress`), Samvid
(`reconciliation_and_recovery_evidence`), and a direct OpenAlice run
(`read_only_workflow_status_approvals_reports`). The persisted status
`f2763c814d7aa556e0588a24a72516d6ac748932957b75de18943ea3105810b5` records
14 domain-artifact nodes, 9 verified domain artifacts, and 14 verified
external inputs. Each
artifact consumed the frozen point-in-time manifest, names all 9 selected IDs,
and now passes operation-specific payload validation (model/feature rows,
candidate replay rows, calculated metrics including walk-forward/CPCV/PBO,
parity counts, stress samples, reconciliation counts, or read-only
approvals/reports as applicable). A mere
package import, compile, manifest read, health probe, or empty marker is
rejected as `domain_artifact_payload_incomplete`; these artifacts remain
operation evidence, not profitability evidence. The DAG records 9 verified
domain nodes; the OpenAlice read-only control-plane node runs even when the
independent LEAN parity node fails. The workflow remains incomplete because
LEAN is unavailable: this host has neither the required `.NET 10` runtime nor
Docker, so no LEAN parity artifact is claimed.

The final persisted promotion decision is `SHADOW_ONLY`. Current reasons are
`research_bundle_incomplete`, `required_node_not_successful`, chronological and
sealed PF/loss-observation failures, `missing_validation_metrics`,
`selected_exact_strategy_oos_not_positive`, missing/invalid p95 and p99 loss
fields, `perturbation_not_stable`, `replay_parity_not_matched`,
`validated_models_missing`, and the independent LEAN node failure. The
per-row cost contract itself is complete. No execution bundle was written.

## Separate decision status

1. **Rapid-engine behavior:** PROVEN with deterministic fake-broker events:
   one valid four-leg intent; independent per-leg preflight, send, ack, and
   fill states; pending-order replace/cancel/expiry; partial fill and partial
   reduction; complete basket close; restart recovery; idempotent
   reconciliation; BUY-to-SELL and SELL-to-BUY reversal; immediate post-close
   rescan; duplicate suppression; and no-martingale/no-uncontrolled-averaging
   checks. The eight measured intervals are persisted in
   `rapid_benchmark_report.json`; decision-to-intent is 0.3 ms and
   close-confirmation-to-rescan is 10 ms in this deterministic proof. No broker
   API was called. Artifact SHA-256:
   `021ca8a4f384baf143d062a8503ddbb79603070ba6154e35cc0facbc3d8b251d`.
2. **Strategy profitability:** NOT PROVEN. The current 34,923-row explicit-
   cost replay and the 10k diagnostic expansion both have zero exact
   identities positive in validation and sealed OOS; no execution bundle is
   authorized.
3. **MT5 DEMO execution:** NOT PROVEN in the current governed run. The runner
   is stopped, no execution bundle exists, and no order was forced.
4. **Remaining blockers:** positive exact-strategy sealed OOS evidence is
   absent; the larger MT5 quote rebuild timed out inside the terminal API;
   promotion-required model-level p95/p99, perturbation-stability, and full
   replay-parity fields are not complete; LEAN parity cannot run without
   `.NET 10` or Docker; and the optional runtime verifier's `tasklist`
   liveness probe still times out on this host. Therefore the execution bundle
   is absent and the governed MT5 DEMO runner must remain stopped.
