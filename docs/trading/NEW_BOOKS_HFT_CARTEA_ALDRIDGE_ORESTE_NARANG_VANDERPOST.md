# New books digest — HFT / Quant extras (Aug 2026)

Full cleaned text (local / Windows zip only — not on GitHub):

| Book | Markdown extract |
|------|------------------|
| Cartea & Jaimungal — *Modelling Asset Prices for Algorithmic and High-Frequency Trading* (2013) | `@docs/trading/books/modelling-asset-prices-for-algorithmic-and-high-frequency-trading-cartea-jaimungal.md` |
| Irene Aldridge — *High-Frequency Trading* (2013) | `@docs/trading/books/high-frequency-trading-a-practical-guide-aldridge.md` |
| Fabio Oreste — *Quantum Trading* (2011) | `@docs/trading/books/quantum-trading-using-principles-of-modern-physics-oreste.md` |
| Rishi K Narang — *Inside the Black Box* (2013) | `@docs/trading/books/inside-the-black-box-narang.md` |
| Hayden Van Der Post — *Quantum Finance* (2023) | `@docs/trading/books/quantum-finance-van-der-post.md` |

PDFs for offline reading: `docs/trading/extra_hft_pdfs/` (private transfer only).

---

## 1. Cartea & Jaimungal (AMF 2013)

**Thesis:** Mathematical models for algo/HFT — mid-price dynamics, inventory, optimal bid/ask posting, regime effects, adverse selection.

**Codeable ideas:** inventory-aware spread widening; regime-dependent κ (fill intensity); post wider when volatility/adverse-selection risk rises; not a retail “100% WR” signal book.

**Aegis:** Useful for MGC/MT5 market-making or quote-aware exits. Needs real bid/ask + inventory state. Do not treat paper math as a guaranteed edge.

---

## 2. Irene Aldridge — *High-Frequency Trading*

**Thesis:** Practical HFT stack — microstructure, latency, market making, statistical arb, risk, transaction costs. Institutional infrastructure matters.

**Codeable ideas:** spread/scalp only when cost ≪ edge; latency/session filters; market-making inventory limits; kill switches; cost as first-class metric.

**Aegis:** Strongest practical HFT constraint book in this batch. Reinforces: delayed IB type-3 data and $2 FX commissions kill naive firehose.

---

## 3. Fabio Oreste — *Quantum Trading*

**Thesis:** Physics metaphors (uncertainty, entanglement analogies) applied to discretionary forecasting.

**Reality check:** Metaphorical / soft TA framing. Not an HFT execution manual. Holy-grail tone ≠ measurable promotion criteria.

**Aegis:** Low priority. Do not use as primary strategy source for MT5 firehose.

---

## 4. Rishi Narang — *Inside the Black Box*

**Thesis:** How real quant/HFT shops think — alpha research, risk, costs, capacity, process. Edges are probabilistic.

**Codeable ideas:** research pipeline; cost-adjusted expectancy; capacity limits; monitoring live vs model drift; no single “guaranteed WR.”

**Aegis:** Process bible for Windows MT5 work. Pair with Davey/Aronson-style holdout discipline already in the repo.

---

## 5. Hayden Van Der Post — *Quantum Finance*

**Thesis:** Quantum-computing + finance strategies (popular / Reactive Publishing style).

**Reality check:** QC-for-finance is mostly research-stage; not a turnkey retail firehose system on MT5 demo.

**Aegis:** Background only. Do not block MT5 implementation on quantum hardware claims.

---

## Combined policy for Windows / MT5

1. Prefer **Aldridge + Narang + Cartea** for cost, inventory, and process gates.
2. Treat Oreste / Van Der Post as non-blocking optional reading.
3. Still require: broker-native data, costs in every report, frozen holdout before any “promoted” label.
4. These books do **not** justify promising 100% WR firehose.
