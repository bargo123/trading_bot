# Continue on Windows

1. Clone: `git clone https://github.com/bargo123/trading_bot.git`
2. Open the folder in **Cursor on Windows**
3. Read **`docs/CHAT_EXPORT_FOR_WINDOWS.md`** — full Mac chat text
4. Then follow MT5 setup below

## MT5 + Python (Windows)

1. Install broker MT5, log in (demo first), keep it open
2. Python 3.11+ 64-bit
3. In `trading_bot\bot`:
```bat
python -m venv .venv
.venv\Scripts\activate
pip install MetaTrader5 pandas numpy PyYAML yfinance
python -c "import MetaTrader5 as mt5; print(mt5.initialize()); print(mt5.account_info()); mt5.shutdown()"
```

## Key results from the Mac chat
- Best measured from $100 all-in: **~$185** (~$1.30/day), not video-style thousands/day
- Config: `bot/config_video_100_attempt.yaml`
- Paper on Mac: `python scripts/run_paper.py --config config_video_100_attempt.yaml`
- MT5 Python API does **not** work on Mac; use this Windows machine
- Repo: https://github.com/bargo123/trading_bot.git

## Next ask for the assistant on Windows
> Wire Aegis to MT5 demo using config_video_100_attempt.yaml and do a smoke test.
