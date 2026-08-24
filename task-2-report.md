# Task 2 Report: Exact Basket Ownership And Broker-Native Limits

## Delivered

- Added `aegis.intel.firehose_basket` with atomic JSON persistence for exact
  basket and ticket ownership records.
- Stored basket identity, hypothesis, family, symbol, side, risk budget, clip
  cap, broker tick value/size, regime, session, immutable entry geometry, and
  per-ticket trigger, clip sequence, cost evidence, entry geometry, and
  initial broker-native risk.
- Extended `TicketMetadata` persistence with the matching basket ownership
  snapshot fields, using atomic replacement writes.
- Added fail-closed `can_add_clip` gating. Additions require a complete,
  validated policy artifact, a fresh same-side trigger, positive continuation
  evidence, normal spread, positive remaining EV, no adverse selection, a
  non-losing basket, available clip capacity, and remaining risk budget.

## TDD Evidence

- RED: `tests/test_firehose_basket.py` failed collection with
  `ModuleNotFoundError: No module named 'aegis.intel.firehose_basket'` before
  production code existed.
- GREEN: `tests/test_firehose_basket.py -q` completed with `6 passed`.
- Full verification: `pytest -q` completed with `1041 passed` in 83.82s.
  The suite emitted one existing `eventkit` deprecation warning about no
  current event loop.

## Scope Kept

- No runner wiring, configuration, Factory, Council, MT5, order placement, or
  live-enablement changes were made.

## Follow-Up Hardening

- Basket creation and ticket admission now acquire a cross-process lock, reload
  the persisted state while locked, validate it, and only then atomically
  persist the accepted state.
- Persistence failures now raise and restore the prior in-memory basket state;
  callers cannot receive a successful admission for a failed write.
- Adds require a finite, fresh broker PnL snapshot (`observed_at` within five
  seconds of `evaluated_at`); missing, stale, non-finite, and losing snapshots
  reject the add.
- Basket limits and proposed risks reject non-finite and non-positive values.
- Added deterministic regressions for stale-process admission, failed writes,
  fresh PnL requirements, and NaN/non-finite risk inputs. Focused verification
  completed with `14 passed`.
- Full follow-up verification: `pytest -q` completed with `1049 passed` in
  82.04s, with the same existing `eventkit` deprecation warning.

## Round 2 Hardening

- Reload now validates every persisted basket and ticket record before it can
  participate in admission. Non-finite values, invalid positive fields,
  malformed geometry/cost maps, duplicate tickets, and invalid clip sequences
  discard the persisted store fail closed.
- Broker-native risk must be strictly positive for the initial ticket as well
  as additions.
- PnL freshness now compares broker `observed_at` against the internal clock
  (or an explicit trusted `now` argument); caller `evaluated_at` is ignored.
- Added regressions for serialized Infinity/NaN values, malformed persisted
  roots, zero-risk initial tickets, and forged equal stale timestamps. Focused
  verification completed with `21 passed`.
- Full Round 2 verification: `pytest -q` completed with `1056 passed` in
  81.68s, with the same existing `eventkit` deprecation warning.

## Round 3 Hardening

- Reload rejects the entire persisted store unless every root key exactly
  matches its embedded `basket_id`.
- Every persisted ticket's risk is recomputed from its immutable entry/stop
  geometry, volume, and its basket's broker tick value and tick size. A
  non-finite or mismatched stored risk fails closed rather than creating risk
  capacity.
- Added regressions for an aliased root key and a reduced finite stored risk.
  Focused verification completed with `23 passed`.
- Full Round 3 verification: `pytest -q` completed with `1058 passed` in
  83.96s, with the same existing `eventkit` deprecation warning.
