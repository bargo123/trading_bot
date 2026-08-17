#!/usr/bin/env python3
"""Hunt a high-hit-rate M1 firehose across every tradeable MT5 product.

Tiny TP / wide SL (Tharp high-WR shape). Harris: skip if spread >= take.
Conservative same-bar: SL wins the tie. Not a live 95% guarantee.
Does not call mt5.shutdown() (keeps the demo terminal up).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402
from aegis.engines.mt5 import MT5Engine  # noqa: E402
from aegis.indicators import ema  # noqa: E402

LOTS = 0.01
MIN_TRADES = 40
LOOKBACK_DAYS = 10


def pip_size(name: str, point: float, digits: int) -> float:
    up = name.upper()
    if "XAU" in up or up.startswith("GOLD"):
        return 0.1
    if "XAG" in up or "SILVER" in up:
        return 0.01
    if "JPY" in up:
        return 0.01
    if digits <= 3:
        return max(point * 10.0, point)
    return 0.0001


def simulate(high, low, close, ema20, entry_shift, tp_dist, sl_dist) -> dict:
    n = len(close)
    wins = 0
    losses = 0
    pnl = 0.0
    i = 30
    while i < n - 2:
        if np.isnan(ema20[i]) or np.isnan(close[i]):
            i += 1
            continue
        side = 1.0 if close[i] >= ema20[i] else -1.0
        entry = close[i] + side * entry_shift
        tp = entry + side * tp_dist
        sl = entry - side * sl_dist
        j = i + 1
        hit = False
        while j < n:
            h = high[j]
            lo = low[j]
            if side > 0:
                hit_sl = lo <= sl
                hit_tp = h >= tp
            else:
                hit_sl = h >= sl
                hit_tp = lo <= tp
            if hit_sl:
                losses += 1
                pnl -= sl_dist
                hit = True
                i = j
                break
            if hit_tp:
                wins += 1
                pnl += tp_dist
                hit = True
                i = j
                break
            j += 1
        if not hit:
            break
        i += 1
    trades = wins + losses
    wr = 100.0 * wins / trades if trades else 0.0
    exp = pnl / trades if trades else 0.0
    return {"trades": trades, "wins": wins, "losses": losses, "wr": wr, "pnl_price": pnl, "exp_price": exp}


def main() -> None:
    live = load_config(ROOT / "config_mt5_demo_m1_scalp.yaml")
    live["allow_live"] = False
    eng = MT5Engine(live)
    eng.connect()
    acct = eng.account()
    if not acct.is_paper:
        raise SystemExit("demo only")
    mt5 = eng._api()
    raw_syms = mt5.symbols_get() or []
    rows = []
    print(f"MT5 demo {acct.account_id} equity={acct.equity:.2f} symbols_get={len(raw_syms)}")

    candidates: list[str] = []
    for item in raw_syms:
        name = str(getattr(item, "name", "") or "")
        if not name:
            continue
        trade_mode = int(getattr(item, "trade_mode", 0) or 0)
        if trade_mode == 0:
            continue
        vmin = float(getattr(item, "volume_min", 0.01) or 0.01)
        if vmin - 1e-12 > LOTS:
            continue
        candidates.append(name)

    # Prefer majors/metals/crypto first, then the rest (cap so this finishes).
    prefer = []
    rest = []
    for name in candidates:
        up = name.upper()
        if any(
            k in up
            for k in (
                "EUR",
                "GBP",
                "USD",
                "XAU",
                "XAG",
                "GOLD",
                "BTC",
                "ETH",
                "NAS",
                "US30",
                "SPX",
                "GER",
                "UK100",
            )
        ):
            prefer.append(name)
        else:
            rest.append(name)
    watch = prefer + rest
    watch = watch[:120]
    print(f"Scanning {len(watch)} products")

    grids = [(1, 20), (1, 30), (2, 20), (2, 30), (2, 40), (3, 30)]

    for name in watch:
        try:
            spec = eng.symbol_spec(name)
        except Exception as exc:
            print(f"  skip {name}: spec {exc}")
            continue
        spread = float(spec["spread_price"])
        point = float(spec["point"] or 0.0001)
        digits = int(spec["digits"])
        pip = pip_size(name, point, digits)
        contract = float(spec["trade_contract_size"])
        tick_val = float(getattr(eng._ensure_symbol(name), "trade_tick_value", 0) or 0)
        tick_sz = float(getattr(eng._ensure_symbol(name), "trade_tick_size", 0) or 0)
        if tick_val > 0 and tick_sz > 0:
            pip_usd = LOTS * tick_val * (pip / tick_sz)
        else:
            pip_usd = LOTS * contract * pip
        if pip_usd <= 0 or pip_usd > 2.0:
            continue
        rt_usd = LOTS * contract * spread
        # JPY-style overstatement: prefer tick_value spread
        if tick_val > 0 and tick_sz > 0 and spread > 0:
            rt_usd = LOTS * tick_val * (spread / tick_sz)
        try:
            bars = eng.bars(name, "1m", LOOKBACK_DAYS)
        except Exception as exc:
            print(f"  skip {name}: bars {exc}")
            continue
        if len(bars) < 400:
            continue
        df = pd.DataFrame(
            {"high": [b.high for b in bars], "low": [b.low for b in bars], "close": [b.close for b in bars]}
        )
        ema20 = ema(df["close"], 20).to_numpy()
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        close = df["close"].to_numpy()
        for tp_pips, sl_pips in grids:
            tp_usd = tp_pips * pip_usd
            if rt_usd >= tp_usd - 1e-12:
                continue
            sim = simulate(
                high,
                low,
                close,
                ema20,
                entry_shift=spread / 2.0,
                tp_dist=tp_pips * pip,
                sl_dist=sl_pips * pip,
            )
            if sim["trades"] < MIN_TRADES:
                continue
            pnl_usd = sim["pnl_price"] / pip * pip_usd if pip else 0.0
            exp_usd = pnl_usd / sim["trades"]
            rows.append(
                {
                    "symbol": spec["name"],
                    "tp_pips": tp_pips,
                    "sl_pips": sl_pips,
                    "trades": sim["trades"],
                    "wr": round(sim["wr"], 2),
                    "exp_usd": round(exp_usd, 4),
                    "pnl_usd": round(pnl_usd, 2),
                    "spread": spread,
                    "rt_usd": round(rt_usd, 4),
                    "tp_usd": round(tp_usd, 4),
                    "pip_usd": round(pip_usd, 4),
                    "bars": len(bars),
                }
            )
            print(
                f"  {spec['name']:12} tp={tp_pips} sl={sl_pips} "
                f"n={sim['trades']:4d} WR={sim['wr']:6.2f}% E$={exp_usd:7.4f} "
                f"PnL$={pnl_usd:8.2f} rt={rt_usd:.3f}",
                flush=True,
            )

    table = pd.DataFrame(rows)
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "firehose_hw_all_products.csv"
    if table.empty:
        print("NO_ELIGIBLE")
        (out_dir / "FIREHOSE_HW_ALL_PRODUCTS.json").write_text(
            json.dumps({"eligible": [], "note": "no symbol cleared spread<take and min trades"}, indent=2),
            encoding="utf-8",
        )
        return
    table = table.sort_values(["wr", "exp_usd", "pnl_usd"], ascending=[False, False, False]).reset_index(drop=True)
    table.to_csv(csv_path, index=False)

    pos = table[table["exp_usd"] > 0]
    hi = pos[pos["wr"] >= 95.0] if not pos.empty else table.iloc[0:0]
    pool = hi if not hi.empty else pos
    if pool.empty:
        pool = table
    # One best grid per symbol, then keep the best symbols.
    best_by_sym = pool.sort_values(["wr", "exp_usd"], ascending=[False, False]).drop_duplicates("symbol")
    winners = best_by_sym.head(12)
    payload = {
        "account": acct.account_id,
        "equity": acct.equity,
        "min_trades": MIN_TRADES,
        "lookback_days": LOOKBACK_DAYS,
        "conservative_sl_tie": True,
        "winners": winners.to_dict(orient="records"),
        "top20": table.head(20).to_dict(orient="records"),
        "note": "Sample WR on MT5 M1 OHLC. Not a live 95% guarantee. SL wins same-bar ties.",
    }
    (out_dir / "FIREHOSE_HW_ALL_PRODUCTS.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print("\n=== WINNERS ===")
    print(winners.to_string(index=False))
    print(f"CSV {csv_path}")
    print("WINNER_SYMBOLS=" + ",".join(winners["symbol"].tolist()))
    if not winners.empty:
        mode = winners.iloc[0]
        print(
            f"PRIMARY={mode['symbol']} tp={mode['tp_pips']} sl={mode['sl_pips']} "
            f"WR={mode['wr']} E$={mode['exp_usd']}"
        )


if __name__ == "__main__":
    main()
