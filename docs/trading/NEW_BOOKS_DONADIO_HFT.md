# Donadio / Ghosh / Rossier — Aegis digest (Aug 2026)

Full extract: `@docs/trading/books/developing-high-frequency-trading-systems.md`
Sebastien Donadio, Sourav Ghosh, Romain Rossier — *Developing High-Frequency Trading Systems* (Packt 2022).

Educational/systems work only. **This book does not authorize 100% WR, 100× equity, FPGA-on-an-i5, or turning MetaQuotes M1 into colocation HFT.**

---

## What the book actually is

A **systems** manual: gateways, book builder, strategy, **OMS**, command-and-control, logging, tick-to-trade measurement, then C++/Java/FPGA/kernel-bypass for *microsecond* shops.

Ch.10: Python is for **analytics and research**. Production HFT hot path is C++/Java. Wrapping C++ into Python is how they mix the two. We stay on Python + MT5 because that is this demo stack — we do **not** rewrite the runner in C++ unless you ask.

---

## Codeable on this MT5 demo (what we shipped)

From Ch.2 (OMS + tick-to-trade) and Ch.7 (live stats, logging off the hot path):

1. **`oms_pretrade`** — reject malformed orders *before* `order_send`: bad qty/side, qty > `mt5_max_lots`, open ≥ `max_positions`, crossed bid/ask, SL/TP on the wrong side of the quote.
2. **`max_quote_age_s`** — skip if the MT5 tick is older than N seconds (stale book). Default **5** on a 1s poll.
3. **Tick-to-trade** — `time.perf_counter()` from quote-in to order-out. Journal field `t2t_ms`; heartbeat `t2t_p50_ms` / `t2t_p95_ms` / `oms_rejects` / `quote_stale`.

Existing clips are not flattened. Only **new** orders hit the OMS.

---

## What we are not shipping

- Kernel bypass, microwave, FPGA, LMAX Disruptor, lock-free C++ order books.
- A second matching engine or a local L2 book builder (MetaQuotes is the venue).
- A claim that 1-second Python polling is HFT.

Those chapters stay fuel. If you later want a C++ tick path, that is a different project.
