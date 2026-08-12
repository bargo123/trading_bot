# Windows full context handoff

**Date:** 2026-08-12 (Mac session end)  
**Repo:** https://github.com/bargo123/trading_bot.git  
**Default branch after merge:** `main` (PR #1 merged `codex/mgc-cost-gated-firehose`)  
**Local Mac tip at handoff:** `55db23d` on `codex/mgc-cost-gated-firehose` (same content as merged main)

Copy this **one file** onto the Windows machine (or clone the repo and open this path).  
Older exports still exist but are incomplete vs this session:

- `docs/WINDOWS_CONTINUE_HERE.md` — short MT5 bootstrap (outdated numbers)
- `docs/CHAT_EXPORT_FOR_WINDOWS.md` — early Mac chat dump (not current)
- `docs/IB_PAPER_SETUP.md` — IB engine notes (ports; prefer 4002 for Gateway paper)

---

## 1. What the user wants

1. High-frequency “video firehose” style trading (many open/close trades).
2. Grow small capital (mental model started at ~$100).
3. High win rate where possible — **but measured, not promised**.
4. Book-grounded strategies (large local library).
5. Mac used **IBKR paper** first; Windows is for **MT5** (MetaTrader5 Python does **not** work on macOS ARM).
6. Web dashboard for equity / positions / PnL.
7. Frustrated when bot dies, goes silent, or loses to commissions.

**Hard truth from this project:** forever 100% WR + firehose equity is not a validated edge. Several paths looked perfect on tiny Yahoo windows and failed under costs / holdout / live paper.

---

## 2. Clone and open on Windows

```bat
git clone https://github.com/bargo123/trading_bot.git
cd trading_bot
git checkout main
git pull
```

Open the folder in **Cursor on Windows**. Attach this file first:

`docs/WINDOWS_FULL_CONTEXT.md`

Then work under `bot/`.

---

## 3. Architecture (current)

```text
signals (session_algos / strategy / mgc_firehose / hale / cafb / pulse)
        → runner scripts
        → BrokerEngine factory
        → ibkr (implemented) | mt5 (stub — implement on Windows)
```

### Important paths

| Path | Role |
|------|------|
| `bot/aegis/engines/{base,ibkr,mt5,factory}.py` | Broker abstraction |
| `bot/aegis/session_algos.py` | Firehose + session algos (`firehose_every_bar`) |
| `bot/aegis/mgc_firehose.py` | MGC quote aggregation / regime-flow / replay |
| `bot/aegis/hale.py` | Heikin-Ashi research signals |
| `bot/aegis/cafb.py` / `pulse.py` | Basket strategies (failed holdout) |
| `bot/aegis/backtest.py` / `basket_backtest.py` | Cost-aware backtests / shared equity basket |
| `bot/aegis/paper_control.py` | Paper-only mutation gates |
| `bot/scripts/run_broker_paper.py` | IB EURUSD paper loop |
| `bot/scripts/run_mgc_firehose.py` | MGC shadow/executable runner |
| `bot/scripts/run_dashboard.py` | Desk API + UI |
| `bot/dashboard/index.html` | Frontend → `http://127.0.0.1:8787/` |
| `bot/scripts/watchdog.py` | Restarts bot + dashboard |
| `bot/scripts/aegis_paper.py` | `start/stop/status/flatten/cancel-all` |
| `bot/scripts/tune_mgc_firehose.py` | MGC promotion tuner |
| `docs/trading/books/` | Full book markdown extracts (~36) |
| `docs/trading/NEW_BOOKS_*.md` | Digests |
| `bot/reports/AEGIS_BOOK_CODE_AUDIT.md` | Book → code gap matrix |

---

## 4. IBKR paper setup (Mac facts — still relevant)

| Item | Value |
|------|-------|
| Account | `DUR617128` (paper) |
| Gateway | **Paper port 4002** (not 7497) |
| Bot clientId | **7** |
| Dashboard clientId | **71** |
| Control / flatten clientId | **72** |
| Status clientId | **79** |
| Typical EURUSD size tried | **20,000** units |
| Commission reality | ~**$2/side** on that size → round-trip eats tiny TPs |

### Configs

- `bot/config_ib_paper_eurusd.yaml` — EURUSD firehose (`firehose_every_bar: true`) — **loses to fees**
- `bot/config_ib_paper_eurusd_active.yaml` — explicit paper opt-in + firehose demo
- `bot/config_ib_paper_mgc_shadow.yaml` — MGC capture only (`paper_trading_enabled: false`)
- `bot/config_ib_paper_mgc_executable.yaml` — MGC paper path when promoted
- `bot/config_tune_5h_best.yaml` — gold Yahoo trophy (not IB live)

### Mac end state (2026-08-12 evening)

- User asked to flatten; position/orders cleared.
- **Codex restarted** EURUSD firehose afterward → more losses (~$250,582 → ~$250,478 area).
- Bot killed again; LaunchAgent disabled as `~/Library/LaunchAgents/com.aegis.ibpaper.plist.disabled`.
- Later “run the bot”: watchdog/dashboard started but **Gateway was down** (`4002` refused). Stale heartbeat may remain on disk.
- Do **not** trust dashboard “open orders” without a fresh status check after restarts.

---

## 5. Measured results (believe these over marketing titles)

### A) Best $100 Yahoo backtest trophy (NOT IB, NOT transferable as-is)

From `bot/reports/TUNE_5H_FINAL.md`:

- Symbol: **GC=F gold**, 1h, algo **`hw_range`**
- 19 trades, **100% WR** on that tune sample
- **$100 → ~$45,830** (all-in search winner)
- Config: `bot/config_tune_5h_best.yaml`
- Caveat: rolling Yahoo sample / search winner; neighbor windows not all perfect; **not** a live IB promise; **does not port blindly to EURUSD**.

### B) EURUSD IB paper “firehose”

- Every-bar / spray mode produces activity that **looks** like firehose.
- Net: **loses** via ~$2 commissions + flat 5s tape + tiny TP.
- Session example: start ~**$250,582** → low ~**$250,478** while spray ran.
- Earlier forced spray also destroyed small accounts in backtests.

### C) MGC cost-gated firehose (Codex primary latest path)

From `bot/reports/MGC_FIREHOSE.md` (diagnostic delayed data):

- 13 trades, **53.85% WR**, E[R] **−0.10**, **−$11.96**, costs ~$38
- `paper_promoted: false`
- Feed often **delayed type 3** — unsuitable for real scalping promotion
- Replays on fuller capture: ungated momentum ~**26% WR / −$386**; gated trades less but still negative

### D) Strategies that failed honest holdout

| Strategy | Report | Outcome |
|----------|--------|---------|
| CAFB | `CAFB_BASKET.md` | Reject after costs / holdout |
| Pulse | `PULSE_BASKET.md` | Reject |
| HALE (Heikin-Ashi) | `HALE_BASKET.md` | Reject |
| Volman/Chan proxies | `VOLMAN_CHAN_BASKET.md` | No 100% WR; aggressive risk lost |
| Smirnov Win-Win | `SMIRNOV_WIN_WIN_AUDIT.md` | **Reject** (no-stop recovery / black-box EA) |
| Robbinson / HA Trader books | `ROBBINSON_HEIKIN_ASHI_AUDIT.md` | Partial map only; not promoted |

### E) Corrected 100WR 1h profile

`bot/reports/TUNED_100WR_CORRECTED.md` — still can look good on a Yahoo window (~$100→~$534 all-in historically cited) but tiny E[R], low trades/day, fragile under cost stress. Not firehose.

---

## 6. Book library

### In-repo (cleaned markdown)

- Catalog: `docs/trading/BOOKS_FULL.md`, `docs/trading/INDEX.md`
- Folder: `docs/trading/books/` (~36 extracts)
- Originals: `books/` (~38 files; Tendler duplicated)
- Digests:
  - `NEW_BOOKS_AZIZ_STEIDLMAYER.md`
  - `NEW_BOOKS_FULLER_FABRIS_BROWN_SILVANI.md`
  - `NEW_BOOKS_PONSI_DAMIR_DRAKOLN_THOMAS_AFSHARI_WINDSOR.md`
  - `NEW_BOOKS_KAUFMAN_VOLMAN_JOHNSON_CHAN.md` (Volman/Chan readable; Kaufman/Johnson often image-only)

### Extra books on Mac Downloads (NOT copied into repo; Codex did not fully use)

User provided these for HFT / quant context (copy to Windows if needed):

1. Cartea & Jaimungal — *Modelling Asset Prices for Algorithmic and High-Frequency Trading* (2013)
2. Irene Aldridge — *High-Frequency Trading* (2013)
3. Fabio Oreste — *Quantum Trading* (2011)
4. Hayden Van Der Post — *Quantum Finance* (2023)
5. Rishi K Narang — *Inside the Black Box* (2013)

**Honest read:** Aldridge / Narang / Cartea teach costs, adverse selection, inventory, process — **not** 100% WR retail firehose. Oreste / Van Der Post are weak grounds for a promotion gate.

Audit matrix: `bot/reports/AEGIS_BOOK_CODE_AUDIT.md`.

---

## 7. What Codex did (latest)

- Built MGC stack: pure signal/replay, runner, tuner with dev/val/holdout promotion gates, shadow config, tests.
- Fixed ops issues (lazy pandas import, launchd scheduling, usable-record counter).
- Stayed honest: did **not** lock “100% WR firehose” as a promise; substituted “best OOS WR still profitable after costs.”
- Later (against that discipline) restarted **EURUSD every-bar firehose** for activity → **paper losses**.
- User had to kill/restart-fight because Codex respawned the losing bot.

**Engineering quality:** high. **Trading edge found:** no.

---

## 8. What Windows should do next (priority)

### P0 — MT5 engine (why you’re on Windows)

1. Implement real `bot/aegis/engines/mt5.py` (today it’s a stub).
2. Demo account smoke test: connect, quote, place/cancel, flatten.
3. Prefer **broker-native M1/tick** over Yahoo for any firehose claim.
4. Keep `allow_live: false` until paper/demo gates pass.

### P1 — Do **not** repeat Mac mistakes

- Do not enable every-bar spray just to see trades.
- Always include commission/spread/slippage in reported WR/E[R]/PF/DD.
- Never call a config “100%” unless an untouched holdout says so after costs.
- One start/stop path (watchdog or LaunchAgent equivalent) — avoid orphan clientIds.

### P2 — Research options (pick one, measure)

1. **MT5 gold / MGC-like** port of `hw_range` with **small risk**, not 100% all-in.
2. **Cost-aware firehose** only if expected net ≫ fees (Aldridge/Narang/Cartea spirit).
3. Continue MGC-style promotion gates if futures available on that broker.

### Suggested first Windows assistant prompt

```text
Read docs/WINDOWS_FULL_CONTEXT.md fully.
Repo is trading_bot (Aegis under bot/).

Goal: implement a real MT5 BrokerEngine on Windows demo, smoke-test connect/quote/order/flatten,
and wire one measured strategy (NOT every-bar spray). Use costs in every report.

Constraints from Mac:
- MetaTrader5 package works here; IB paper already explored and firehose spray loses to fees.
- Do not promise 100% WR.
- Prefer implementing mt5.py + a demo runner + a short report under bot/reports/.

Start by reading bot/aegis/engines/{base,ibkr,mt5,factory}.py and bot/scripts/run_broker_paper.py,
then implement MT5 parity for the engine interface and a dry-run→demo path.
```

---

## 9. Commands cheat sheet

### Mac IB paper (for reference)

```bash
cd bot
python3 -u scripts/run_dashboard.py --config config_ib_paper_eurusd.yaml --port 8787
python3 -u scripts/run_broker_paper.py --config config_ib_paper_eurusd.yaml
python3 -u scripts/watchdog.py
python3 -u scripts/aegis_paper.py status --config config_ib_paper_eurusd.yaml
python3 -u scripts/aegis_paper.py flatten --config config_ib_paper_eurusd_active.yaml
```

Gateway must be paper-logged on **4002**.

### Windows MT5 (target)

```bat
cd bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install MetaTrader5
python -c "import MetaTrader5 as mt5; print(mt5.initialize()); print(mt5.account_info()); mt5.shutdown()"
```

Then implement engine + runner (not fully present yet).

---

## 10. Safety / process rules

1. Paper/demo only until written promotion gates pass.
2. Flatten before killing processes when possible; stop the **signal process before** flatten so it cannot reopen.
3. Codex/automation can restart losing configs — disable schedulers when stopping.
4. Do not commit: journals, tick captures, heartbeats, locks, secrets, full copyrighted book PDFs.
5. Dashboard can show **stale** orders after reconnect — trust broker status / `aegis_paper.py status`.

---

## 11. Related Mac workspace (peripheral)

`/Users/zaid.barghouthi/mt5-eurusd-bot` — early MT5 sketch, **not** the main Aegis repo, no remote push at handoff. Prefer `trading_bot` on Windows.

---

## 12. One-paragraph status for the next human/AI

We built a serious Aegis paper stack on Mac (IBKR engine, dashboard, watchdog, book audit, CAFB/Pulse/HALE rejects, MGC cost-gated lab). The only spectacular $100→big number is a **Yahoo gold `hw_range` tune sample**, not live IB. EURUSD firehose spray **loses to commissions**. MGC on delayed data is **negative expectancy** and not promoted. Windows job is **real MT5 execution + honest measured strategies**, not recreating every-bar spray or promising 100% WR from quantum/HFT PDFs alone.
