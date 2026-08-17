# Optimizer agent prompt (optional Cursor CLI)

The live demo YAML `config_mt5_demo_firehose_hw.yaml` is protected. Do not copy onto it.
Research lives in `bot/aegis/research/` (shadow only). Start from the registry, not chat memory.
Unattended Cursor CLI stays off (`with_cursor: false`). The optimizer cycle now runs research holdout gates: no synthetic accepts, no negative E, win rate alone never promotes.

Demo R&D: invent aggressively (YAML patches this cycle). Prefer **more dollars after costs** (Tharp E / net PnL), not a WR trophy. Hunt EURUSD 1-pip / 30-pip printed 95.24% WR and **lost money** — do not promote that shape if OOS E is worse.

Keep `firehose_every_bar: true` and 24h **unless** a measured patch is the experiment. Never stop the research loop. Never set `allow_live`.

Read **all** of these each proposal (library digests; full texts live under `docs/trading/books/`):

1. `bot/optimizer/optimizer_state.md`
2. `bot/optimizer/current_best.json`
3. `docs/trading/INDEX.md`
4. `docs/trading/NEW_BOOKS_CORE_TWELVE.md`
5. `docs/trading/NEW_BOOKS_AEGIS_MT5_FOREX_BATCH.md`
6. `docs/trading/NEW_BOOKS_HFT_CARTEA_ALDRIDGE_ORESTE_NARANG_VANDERPOST.md`
7. `docs/trading/NEW_BOOKS_KAUFMAN_VOLMAN_JOHNSON_CHAN.md`
8. `docs/trading/NEW_BOOKS_FULLER_FABRIS_BROWN_SILVANI.md`
9. `docs/trading/NEW_BOOKS_PONSI_DAMIR_DRAKOLN_THOMAS_AFSHARI_WINDSOR.md`
10. `docs/trading/NEW_BOOKS_AZIZ_STEIDLMAYER.md`
11. `docs/trading/NEW_BOOKS_VPA_BROOKS_DAMIR.md`
12. `docs/trading/NEW_BOOKS_HARRIS_JANSEN.md`
13. `docs/trading/NEW_BOOKS_DONADIO_HFT.md`

Propose **one** YAML patch. Output JSON only:

```json
{"id": "short_slug", "patch": {"firehose_tp_pips": 2}, "weakness": "high_wr_neg_e", "rationale": "..."}
```

Rules:
- Do not place orders. Do not call `mt5.shutdown()`. Do not flatten.
- Do not edit live YAML while heartbeat `open > 0`.
- Never set `firehose_every_bar` false. Never shrink session off 24h. Never cut `max_positions`.
- Authors disagree (Tharp/Davey dollars vs high-WR scalp). Default: dollars on firehose, not a new system.
- Educational/systems work only. No profit guarantees.
