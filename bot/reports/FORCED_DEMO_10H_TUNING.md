# Forced Demo: 10-Hour Paper Tuning Log

Start: 2026-08-12 00:12:26 UTC

## Baseline

- Paper equity at tuning start: $250,510.76
- Forced-demo equity before the first cycle: $250,526.06
- Pre-tuning forced-demo change: -$15.30
- Quantity: 20,000 EURUSD
- Target: 6 pips
- Stop: 5 pips
- Maximum hold: 45 seconds
- Every-bar demo: enabled
- Live trading: disabled
- Tuning-period halt floor: $250,410.76

## Protocol

- Observe every five minutes for ten hours.
- Measure real completed paper cycles after commissions and equity changes.
- Require 20 new closed cycles before changing a parameter.
- Change only one of target pips, stop pips, or maximum hold per tuning step.
- Restart only while flat with no working or cancelling orders.
- Never raise quantity above 20,000 or weaken the paper/live boundary.
- Halt and flatten on the loss floor, non-paper broker state, or inconsistent order lifecycle.

## Changes

No tuning change yet; collecting the first 20-cycle sample.
