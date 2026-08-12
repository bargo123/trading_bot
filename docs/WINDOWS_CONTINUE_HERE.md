# Continue on Windows

**Primary handoff (read this first):**  
[`docs/WINDOWS_FULL_CONTEXT.md`](WINDOWS_FULL_CONTEXT.md)

That file has the full Mac session context: architecture, IB paper facts, measured wins/losses, books, Codex work, and the Windows MT5 plan.

## Quick start

```bat
git clone https://github.com/bargo123/trading_bot.git
cd trading_bot
git checkout main
git pull
```

Open in Cursor → attach `docs/WINDOWS_FULL_CONTEXT.md`.

## MT5 smoke (Windows only)

```bat
cd bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install MetaTrader5
python -c "import MetaTrader5 as mt5; print(mt5.initialize()); print(mt5.account_info()); mt5.shutdown()"
```

## Older files

- `docs/CHAT_EXPORT_FOR_WINDOWS.md` — early chat dump (incomplete vs Aug 12)
- `docs/IB_PAPER_SETUP.md` — IB engine notes
