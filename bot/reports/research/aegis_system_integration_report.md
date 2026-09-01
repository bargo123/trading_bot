# AEGIS system integration

## Data flow

`MT5Engine.quote()` → normalized broker quote → `MarketEvent` →
`EventLedger` → `QuoteBuffer` → Firehose brain / Watcher advisory.

The Watcher advisory evaluates the exact point-in-time symbol, side, mechanism,
and horizon state using the existing authored algorithm modules. It is journaled
as research evidence only. It cannot create an `OrderRequest` or call a broker.

The execution path remains:

`candidate` → existing Firehose gates → `OrderRequest` →
`run_broker_paper.py` → `MT5Engine.place_order()` → existing MT5
`order_check`/`order_send` path.

The runner now emits versioned `OrderIntent`, `PreflightResult`, acknowledgement,
execution, fill, position, close, outcome, and reconciliation contracts around
that path. Confirmed close learning remains broker-evidence based.

## Runtime verification and deliberate limits

The verified source was loaded by a controlled restart. The one logical runner
is PID 27232 (venv launcher PID 20292), connected to `MetaQuotes-Demo`, with a
healthy feed, trading eligibility true, zero open positions, 19 accepted causal
events and active scans. The raw server-clock timestamp defect is no longer a
global quote-admission halt.

No legitimate candidate fired after restart because the short-horizon artifact
remains `SHADOW_ONLY_NO_POSITIVE_OOS`; therefore this pass does not prove a new
broker fill, rapid live close, live pending ladder, live reversal, or
post-close timing. No signal was forced and no book perspective authorizes or
suppresses production execution.
