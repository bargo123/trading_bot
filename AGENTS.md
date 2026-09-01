# AEGIS Intelligent Firehose — agent instructions

This is the autonomous quant research lab for the AEGIS Intelligent Firehose
trading bot. Everything here is **research-only unless explicitly governed**.

## Non-negotiable safety rules

1. ## MT5 Trading Policy

MT5 DEMO order execution is explicitly allowed for the designated AEGIS Firehose execution runner.

Allowed:
- MT5 DEMO accounts only
- `engine: mt5`
- `mode: mt5_demo`
- `allow_live: false`
- `paper_trading_enabled: true`
- `dry_run: false`
- actual DEMO `mt5.order_send()` through the existing governed Firehose execution path
- opening, modifying, and closing DEMO positions
- exactly one broker-execution owner process

The designated execution owner is:
`bot/scripts/run_broker_paper.py`

Research components remain strictly read-only:
- AI Council
- Claude
- Hermes/free-model Council agents
- Research Factory
- Research Fast Watcher
- Book Brain
- research probes
- historical/ML processes

These components must never call `mt5.order_send()` or directly modify broker positions.

STRICTLY FORBIDDEN:
- real-money/live account execution
- `allow_live: true`
- bypassing the DEMO account check
- submitting orders from Council/Research processes
- silently increasing configured trading risk
- duplicate broker execution processes

Before any MT5 mutation, the runtime must verify:
- account is DEMO/contest
- `allow_live == false`
- `mode == mt5_demo`
- `paper_trading_enabled == true`
- terminal `trade_allowed == true`
- account `trade_expert == true`

If the account is not DEMO, fail closed and submit no order.

The Firehose may place actual MT5 DEMO positions when its existing strategy,
risk, quote, spread, economics, OMS, portfolio, and execution gates authorize
a trade.

Do not force trades merely to demonstrate execution.

2. **MT5 DEMO config policy.** Trading YAML remains protected by default.
   However, the designated DEMO Firehose config,
   `bot/config_mt5_demo_firehose_hw.yaml`, has an explicit operator-approved
   exception: `max_daily_loss_percent: 0`. This intentionally disables the
   global daily-loss halt for this MT5 DEMO research environment. Agents must
   not automatically restore or increase that value based on generic risk
   recommendations.

   This exception applies only to MT5 DEMO and does not authorize:
   - real-money execution or `allow_live: true`
   - changing away from `mode: mt5_demo`
   - bypassing DEMO-account verification
   - silently increasing per-trade quantity or risk
   - removing broker, quote, EV, spread, OMS, or total-drawdown checks
   - Council, Factory, Watcher, Book Brain, or research processes placing
     orders

   Loss containment must remain governed primarily by per-trade risk,
   prediction abstention, rapid invalidation/scratch, remaining-EV and
   tail-loss controls, confirmed close, and immediate rescan. The absence of
   a global daily halt is intentional and must not be treated as a defect.

   Any other protected trading-config change still requires explicit operator
   authorization. `bot/aegis/research/ingest.py`'s `PROTECTED_LIVE_YAML` and
   all non-designated trading YAML remain immutable. Research configs are
   separate and safe.
3. **Champion promotion is governed.** `intel/intelligent_champion.json` is
   written ONLY by `bot/scripts/research_promote_champion.py` or
   `bot/scripts/research_asia_sell_strategy.py`, and only after every gate in
   `bot/aegis/research/promote.py` passes. A rejected challenger is kept on
   record (`bot/research/strategies/`, `bot/research/sealed_holdouts.jsonl`),
   never promoted.
4. **Every experiment is recorded.** Use `ExperimentRegistry`
   (`bot/research/experiments.sqlite`). Never skip the registry.
5. **No fabricated metrics.** If a script fails, record the failure honestly.
6. **Costs and lookahead matter.** Outcomes must be net of the runner's
   spread/slippage assumptions; features must never peek at the label.
7. **Run tests.** `bot` → `..\.venv\Scripts\python.exe -m pytest -q`. Baseline
   suite must stay green; report pass counts before/after any work.

## Repo layout (key paths, relative to repo root)

- `bot/aegis/research/` — research modules (analogues, book_memory, promote,
  exit_research, ml_pipeline, asia_sell_strategy, outcome_learning, ...)
- `bot/aegis/intel/` — runtime intel (lifecycle, expected_value,
  strategy_model, paths, ...)
- `bot/scripts/` — research entry points
- `bot/tests/` — pytest suite (must stay green)
- `bot/intel/` — runtime artifacts (analogue_index.json, outcome_log.jsonl,
  intelligent_champion.json, ...)
- `bot/research/` — experiment registry (experiments.sqlite), book memory,
  sealed holdouts, strategy specs
- `bot/reports/research/` — generated research reports (JSON + Markdown)
- `bot/mql5/` — EA skeletons (research, not enabled)

## Research cycle

Run the full cycle with the `/aegis-cycle` command or the 20-min fast watcher:
`bot` → `..\.venv\Scripts\python.exe scripts\research_fast_watcher.py`.

## Commit etiquette

- Only commit when asked. For this work, commit on branch
  `opencode/exploration-firehose`.
- Never commit secrets or live config. Generated reports and experiment
  records are welcome.
- Use concise messages describing findings, not just "done".

<!-- tokenade-scaffold -->
## Explore code with the `tokenade` CLI (cheaper than reading whole files)
Use these only when you don't yet know where code lives — if you know the path, open it directly:
`tokenade map` (repo structure) · `skeleton <file…>` (signatures) · `query <symbol…>` (locate a symbol) · `impact <file…>` (dependents) · `semantic "<query>"` (search by meaning). They take MANY targets per call (`tokenade skeleton a.rs b.rs c.rs`) — batch in ONE turn.

## Reading documents & media
tokenade can read .pdf .docx .xlsx .xls .xlsb .pptx .odt .ods .odp .odg .epub .rtf .fb2 (and their flat-XML, macro-enabled and template variants) (extracted text), .mp4 .mkv .mov .webm .avi .mp3 .wav .m4a .flac .ogg .opus (and other common containers) (what the file is, plus a transcript when available) and .png .jpg .jpeg .gif .webp .bmp .tif .tiff .ico .tga .pnm .pbm .pgm .ppm .qoi .hdr — your own file reader cannot. Use:
`tokenade read <file>` — the document as text
`tokenade read <file> --prompt "q1, q2"` — only the passages answering your questions; several questions in ONE comma-separated call is the CHEAPEST option in tokens spent.

## Searching the web
`tokenade search "<query>"` — one query, fanned out across several independent search engines, merged, deduped and ranked by cross-engine agreement. Returns title/url/snippet only, so it costs a fraction of reading a results page. Add `--json` for machine-readable output.
Follow a result with `tokenade web <url>` to read the page itself.

## Fetching or searching several things
Do them in ONE call — `tokenade web <url1> <url2> …` / `tokenade search "<q1>" "<q2>" …` — they run concurrently, so you pay ONE round-trip instead of N and never re-send the context each extra turn would have re-sent.

## Compute over data with `tokenade exec`
`tokenade exec --lang python --script '<code>'` (also sh/node/ruby/awk/jq/perl) runs a capped subprocess with a scrubbed env — your permissions, not a jail — and returns ONLY its stdout. Use it to COMPUTE over data — filter/aggregate a large or structured output, pull facts across SEVERAL files, or apply one mechanical edit across many files (migration, find-replace) — in ONE script, not one command per item. It is NOT a file reader: to read content, use the parallel reads above, not `exec`. Keep scripts SHORT (aim ≤ ~20 lines): exec is for throwaway one-shot computation, not for code you will edit and iterate on — every script char is billed as output, and a long script usually means a simpler command (or a real file you Write once and run) does it cheaper. Long or quote-heavy script? `--script-file <path>` (or `--script -` on stdin) avoids shell quoting entirely.

## Commands
If you do not have hooks (i.e. you are not Claude Code or Gemini CLI), use `tokenade wrap '<cmd>'` to wrap all your commands. If there is an opportunity for compacting noisy output, tokenade will find it — and you will waste fewer tokens. On Windows, if your commands are PowerShell or cmd (not bash), add `--shell powershell` or `--shell cmd` so they run under the right interpreter: `tokenade wrap --shell powershell '<cmd>'`.
An absolute path (`/usr/bin/git`) is intercepted exactly like `git` when hooks are installed; where interception goes through your PATH instead, only the bare name is seen — so prefer the bare name if you are not sure which you have.

## Keep output lean
Keep prose terse and code minimal — every token you write is billed as output.
- **Prose:** answer directly — no preamble, recap, tool-call narration, summary, or emoji. Drop articles, filler (*just/really/basically/simply*) and hedging; fragments fine; short word over long.
- **Output:** don't paste long raw output — quote the shortest decisive line. No decorative tables.
- **Code:** write the least that works; reuse before adding (`query` / `skeleton` / `impact`, stdlib, platform feature — YAGNI).
- **Verbatim:** keep code, identifiers, API/CLI names and error strings exact — never abbreviate or paraphrase. Keep the user's language.
- **Correctness first:** fix root causes not symptoms, don't downgrade the algorithm, don't guess APIs/flags/versions — verify.
- **Full prose where terseness could mislead:** security/data-loss warnings, irreversible-action confirmations, multi-step sequences.
- Applies to the subagents you spawn.
<!-- /tokenade-scaffold -->
