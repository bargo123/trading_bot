from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd


def fetch_ohlcv(symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
    """Fetch OHLCV via yfinance (works on macOS without a broker)."""
    import yfinance as yf

    interval_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "1d": "1d",
    }
    interval = interval_map.get(timeframe)
    if not interval:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    days = int(lookback_days)
    if interval == "1m":
        days = min(days, 7)
    elif interval in {"5m", "15m"}:
        days = min(days, 59)
    elif interval == "1h":
        days = min(days, 729)  # Yahoo hard-caps ~730d for 1h

    # Prefer period= to avoid off-by-one start/end rejections from Yahoo
    period = f"{max(days, 1)}d"
    df = yf.download(
        symbol,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
    )
    if df is None or df.empty:
        # Fallback: daily bars if intraday unavailable for this symbol
        if interval != "1d":
            df = yf.download(
                symbol,
                period="max",
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
        if df is None or df.empty:
            raise RuntimeError(f"No data returned for {symbol} ({interval})")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]

    df = df.rename(columns={"adj close": "close"})
    out = df[["open", "high", "low", "close", "volume"]].copy()
    out = out.dropna()
    out["time"] = pd.to_datetime(out.index, utc=True)
    out = out.reset_index(drop=True)
    return out


def add_spread_proxy(df: pd.DataFrame, spread_bps: float) -> pd.DataFrame:
    out = df.copy()
    out["spread"] = out["close"] * (spread_bps / 10000.0)
    return out
