# Firehose Basket Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development task-by-task.

**Goal:** Add Book-Brain evidence packets, exact persistent Firehose basket ownership, and chronological basket-policy validation without enabling unvalidated runtime behavior.

**Architecture:** Research owns corpus retrieval, contradiction evidence, replay, walk-forward, and policy artifacts. Runtime owns exact ticket/basket lifecycle and consumes a policy only when its complete validated artifact exists. Existing Research Factory and AI Council remain independent.

**Tech Stack:** Python, existing BookIndex/knowledge APIs, dataclasses, pytest, broker-native math, JSONL.

**Spec:** `docs/superpowers/specs/2026-08-24-firehose-basket-evidence-design.md`

## Global Constraints

- Do not alter Research Factory, AI Council, Book Brain, ML, replay, governance, entry gates, risk YAML, or DEMO safety.
- No order placement, MT5 runner launch, external CLI, live enablement, or fabricated source/data/policy evidence.
- `allow_live=false` and `exploration_max_risk_per_trade_usd=0.15` remain unchanged.
- Missing book, cost, lifecycle, or OOS evidence returns `NO_EVIDENCE` or `NOT_IMPLEMENTED`.

---

### Task 1: Full-Corpus Evidence Packets

**Files:**
- Create: `bot/aegis/research/firehose_basket_evidence.py`
- Create: `bot/tests/test_firehose_basket_evidence.py`

**Interfaces:** Produces `build_evidence_packet(index, hypothesis, support_query, contradiction_query, data_observation, falsification) -> dict`.

- [ ] Write RED tests: multi-source packet preserves source hash/location/passage; contradiction is stored; no matches gives `BOOK_COVERAGE=INSUFFICIENT`; novel origin is allowed only as `NOVEL_SYNTHESIZED_HYPOTHESIS`; no source is invented.
- [ ] Run `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_evidence.py -q`; expect import failure.
- [ ] Implement by calling existing `BookIndex` and `search_full_book_knowledge`; preserve verbatim provenance, reject empty direct-source claims, and emit JSON-serializable evidence packets.
- [ ] Run focused tests; commit `feat: add firehose basket evidence packets`.

### Task 2: Exact Basket Ownership And Broker-Native Limits

**Files:**
- Create: `bot/aegis/intel/firehose_basket.py`
- Modify: `bot/aegis/intel/ticket_metadata.py`
- Create: `bot/tests/test_firehose_basket.py`

**Interfaces:** Produces `BasketMetadataStore`; `BasketDecision`; `can_add_clip(basket, continuation, proposed_risk) -> (bool, str)`.

- [ ] Write RED tests: exact basket/ticket metadata survives restart; total broker-native risk never exceeds budget; clip cap; same-side continuation requirement; losing basket cannot add; opposite-side self hedge rejects.
- [ ] Run focused test; expect import failure.
- [ ] Implement atomic persistence and risk math with tick value/tick size; include trigger ID, clip sequence, cost, regime, session, and immutable entry geometry. No policy artifact yields no clip addition.
- [ ] Run focused tests; commit `feat: persist firehose basket ownership`.

### Task 3: Chronological Basket Replay And Policy Gates

**Files:**
- Create: `bot/aegis/research/firehose_basket_replay.py`
- Create: `bot/tests/test_firehose_basket_replay.py`

**Interfaces:** Produces `evaluate_basket_policies(rows, policy_packets) -> dict`.

- [ ] Write RED tests: future data is rejected; costs required; OOS/sealed rows never tune; missing evidence returns `NO_EVIDENCE`; winner selected by costed expectancy/PF/tail/drawdown, not WR.
- [ ] Run focused test; expect import failure.
- [ ] Implement chronological train/validation/walk-forward/OOS accounting for structural, harvest, extension, floor, EV, scratch, and combined policies. Emit a validated artifact only for complete OOS evidence; otherwise no artifact.
- [ ] Run focused tests; commit `feat: validate firehose basket policies`.

### Task 4: Runtime Basket Observability Only

**Files:**
- Modify: `bot/scripts/run_broker_paper.py`
- Modify: `bot/aegis/intel/firehose_turnover.py`
- Create: `bot/tests/test_firehose_basket_runtime.py`

- [ ] Write RED tests: exact basket trace fields; restart ownership; confirmed full basket close releases slots; stale trigger rejects and fresh trigger permits; no artifact means legacy behavior/no basket add; no Research Factory/Council imports.
- [ ] Run focused test; expect missing basket integration.
- [ ] Integrate metadata and append-only traces only after broker-confirmed fills/closes. Do not start orders, change entries, or activate a policy without Task 3 artifact.
- [ ] Run Firehose, Factory, Council focused tests and full pytest; commit `feat: trace firehose basket evidence`.

### Task 5: Final Verification

- [ ] Run existing Book Brain, Research Factory, Council, Firehose, and full suites; verify Factory `--help`, Council imports, and DEMO safety values.
- [ ] Run basket evidence/replay scripts on existing data; report `NO_EVIDENCE` honestly if data is insufficient/corrupt.
- [ ] Review safety diff, commit docs, push branch without merge. Do not launch MT5 due binding repository order-placement prohibition.
