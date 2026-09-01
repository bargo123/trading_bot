# Rapid basket behavior report

Status: **offline behavior verified; live multi-leg proof unavailable**.

The governed runner remains the sole broker-mutation owner. Offline tests cover
global allocation, restart-safe basket ownership, same-thesis clip protections,
pending replacement/cancellation/expiry, partial-fill state, confirmed-close
cleanup, reconciliation and immediate slot release. The exact results are
`184 passed in 18.22s`, `315 passed in 5.84s`, and full pytest
`3047 passed, 1 warning in 155.40s`.

The deterministic local benchmark processed 256 events at 250 ms, 50 ms and
10 ms intervals with p95 bookkeeping latency of 0.0061 ms, 0.0049 ms and
0.0062 ms. This is transport/lifecycle evidence, not broker or full decision
latency.

After the verified restart, PID 27232 is running against `MetaQuotes-Demo` with
a healthy feed, trading eligibility true, 19 accepted causal events and active
scanning. No legitimate candidate fired, so no live four-leg burst, pending
ladder, partial fill, reversal or broker-latency claim is made.

`allow_live=false`; no signal was forced and external research remains
read-only.
