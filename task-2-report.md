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
