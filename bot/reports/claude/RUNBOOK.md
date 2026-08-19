# Aegis on this machine — setup, run, rollback

Written during the new-machine takeover. Environment details are in
[`environment.md`](environment.md); the architecture map is in
[`repo_map.md`](repo_map.md).

## 1. Environment

Python 3.12 was installed via winget. **The `python.exe` on PATH is a Microsoft
Store stub and does not work** — always use the venv interpreter.

```bash
.venv/Scripts/python -m pytest -q
```

Recreate the venv from scratch:

```bash
"$LOCALAPPDATA/Programs/Python/Python312/python.exe" -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt -r bot/requirements.txt
```

## 2. Serena (semantic code navigation)

The default node-based `python` (pyright) backend fails to start on this host, so
`.serena/project.yml` uses the pure-Python `python_jedi` backend, which needs
`jedi-language-server` on PATH.

```bash
uv tool install --from git+https://github.com/oraios/serena serena-agent && uv tool install jedi-language-server
```

Re-index after large refactors (280 files, ~35s):

```bash
serena project index .
```

Health check:

```bash
serena project health-check .
```

The MCP server is registered in `.mcp.json` at the repo root.

## 3. MT5 demo

Verify connectivity read-only — this places no orders:

```bash
.venv/Scripts/python bot/scripts/claude_mt5_check.py
```

Expected: `trade_mode: DEMO`, server `MetaQuotes-Demo`, 26/26 symbols usable.
Results are written to `mt5_demo_check.json`.

> **The MT5 terminal reports `trade_allowed: false`.** Algo Trading is toggled off
> in the terminal, so the bot can read quotes but cannot send orders. Enable
> *Tools → Options → Expert Advisors → Allow algorithmic trading* in MT5 when you
> want the demo runner to actually place orders. Leaving it off is a safe
> observation mode.

### Safety invariants — all must hold

| invariant | where |
| --- | --- |
| `allow_live: false` in every MT5 demo config | `bot/config_mt5_demo_*.yaml` |
| live account refused unless `allow_live` | `bot/aegis/engines/mt5.py:150`, `:200` |
| analogue builder refuses live-account terminal | `bot/scripts/build_real_analogue_index.py` |
| `paper_trading_enabled` must be true to send orders | `bot/aegis/paper_control.py:32,40` |
| IB baseline config is observation-only | `bot/config_ib_paper_eurusd.yaml` |

**Never set `allow_live: true`.** Doing so is the single change that permits
real-money orders.

## 4. Rebuilding the analogue index

The committed `bot/intel/analogue_index.json` is a **synthetic fixture**: 640
records, two outcome values (`-0.02`, `+0.04`) on a mechanical time grid, which
reports a fabricated profit factor of 6.0 for any query with 20 matches. The
runtime now refuses non-measured provenance, so a real index is required before
the Intelligent Firehose will fire.

```bash
.venv/Scripts/python bot/scripts/build_real_analogue_index.py --bars 6000 --step 15 --workers 10
```

Takes ~15 minutes for 26 symbols (state is rebuilt per sampled bar, so it is
O(n²) per symbol and fans out across processes). Verify provenance afterwards:

```bash
.venv/Scripts/python -c "import json;d=json.load(open('bot/intel/analogue_index.json'));print(d['provenance'],d['outcome_unit'],d['n'])"
```

`provenance` must read `mt5_m1`, not `synthetic_proxy` or `research_proxy`.

## 5. Running the demo

```bash
.venv/Scripts/python bot/scripts/run_broker_paper.py --config bot/config_mt5_demo_firehose_hw.yaml
```

## 6. Reporting

```bash
.venv/Scripts/python bot/scripts/claude_firehose_comparison.py
```

Writes `firehose_comparison.md` / `.json` — old vs intelligent payoff structure.
Also available: `claude_analyse_analogues.py` (journal/index aggregates),
`claude_books_inventory.py` (corpus health), `claude_env_report.py`.

## 7. Rollback

Work is on branch `claude/intelligent-firehose`. Upstream `main` is untouched at
`c3039d7`.

| checkpoint | commit | what it contains |
| --- | --- | --- |
| baseline as cloned | `c3039d7` | upstream `main`, 464 passed / 5 failed |
| test baseline repaired | `cc9e45e` | HALE routing, IB observation-only, portable UID. 469 passed |
| per-trade EV gate | `7a30d8e` | `trade_economics.py`, provenance integrity. 497 passed |
| edge-derived sizing | `bbd0722` | `thesis_sizing.py`, parallel index builder. 513 passed |
| drawdown breaker + docs | `5d65276` | risk limits restored to 10%/25%, runbook, reports |
| measured index + fixes | `57dc60f` | real `mt5_m1` index, `resolve_bot_path`, future-quote gate, cross-symbol pooling. 527 passed |

Roll back one step:

```bash
git -C . revert --no-commit <commit> && git -C . commit -m "Revert <commit>"
```

Abandon everything and return to upstream:

```bash
git -C . checkout main
```

### Disabling the new behaviour without reverting code

Every new gate is config-driven, so the runner can be returned to its previous
behaviour from `bot/config_mt5_demo_firehose_hw.yaml`:

| key | set to | effect |
| --- | --- | --- |
| `intelligent_min_payoff_ratio` | `0` | stop rejecting low-payoff geometry |
| `intelligent_min_expected_net_usd` | large negative | stop rejecting negative-EV trades |
| `intelligent_edge_sizing` | `false` | revert to a fixed `order_quantity` clip |
| `intelligent_allow_synthetic_evidence` | `true` | allow the synthetic index to validate strategies (offline/research only) |
| `intelligent_firehose` | `false` | bypass the brain entirely, back to CORE heuristics |

`max_daily_loss_percent` and `max_total_drawdown_percent` were `0` (guards fully
disabled) and are now `10` / `25`. Setting them back to `0` disables the
drawdown circuit breaker — see `bot/aegis/risk.py:61,65`.
