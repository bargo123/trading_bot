"""Pick the next YAML patch from live metrics. Works without Cursor."""
from __future__ import annotations

from typing import Any

from aegis.config import configured_symbols
from aegis.optimizer.cursor_cli import ALLOWED_YAML_PATCH_KEYS

FROZEN_WHILE_PENDING = ALLOWED_YAML_PATCH_KEYS


def pending_frozen_keys(live_cfg: dict[str, Any], accepted_cfg: dict[str, Any]) -> set[str]:
    """Keys already diverged live vs accepted — do not stack another patch on them until promote."""
    frozen: set[str] = set()
    for key in FROZEN_WHILE_PENDING:
        if live_cfg.get(key) != accepted_cfg.get(key):
            frozen.add(key)
    return frozen


def patch_hits_frozen(patch: dict[str, Any] | None, frozen: set[str]) -> bool:
    return bool(frozen.intersection(patch or {}))


def core_live_frozen_keys(live_cfg: dict[str, Any]) -> set[str]:
    """While live YAML is CORE 1/30, never queue TP/SL patches against it."""
    try:
        tp = float(live_cfg.get("firehose_tp_pips") or 0)
        sl = float(live_cfg.get("firehose_sl_pips") or 0)
    except (TypeError, ValueError):
        return set()
    if abs(tp - 1.0) < 1e-12 and abs(sl - 30.0) < 1e-12:
        return {"firehose_tp_pips", "firehose_sl_pips"}
    return set()


CORE_PROTECT_KEYS = (
    "firehose_tp_pips",
    "firehose_sl_pips",
    "firehose_every_bar",
    "session_start_utc",
    "session_end_utc",
    "order_quantity",
    "max_positions",
    "allow_live",
    "signal_mode",
    "algo",
    "max_daily_loss_percent",
    "max_total_drawdown_percent",
    "firehose_anchor_quote",
)


def preserve_core_live_keys(live_cfg: dict[str, Any], accepted_cfg: dict[str, Any]) -> dict[str, Any]:
    """Copy optimizer accepts onto live, but keep CORE 1/30 / 24h / 0.01 / DD-off."""
    out = dict(accepted_cfg)
    for key in CORE_PROTECT_KEYS:
        if key in live_cfg:
            out[key] = live_cfg[key]
    return out


def pick_hypothesis(
    live_metrics: dict[str, Any],
    cfg: dict[str, Any],
    rejected: set[str],
    blocked_keys: set[str] | None = None,
) -> dict[str, Any] | None:
    wr = float((live_metrics.get("metrics") or live_metrics).get("win_rate") or 0.0)
    exp = float((live_metrics.get("metrics") or live_metrics).get("expectancy") or 0.0)
    exp_r = float((live_metrics.get("metrics") or live_metrics).get("expectancy_r") or exp)
    spread_skips = int(live_metrics.get("spread_skips") or 0)
    consec_l = int((live_metrics.get("metrics") or live_metrics).get("max_consecutive_losses") or 0)
    symbols = configured_symbols(cfg)
    tp = int(cfg.get("firehose_tp_pips") or 1)
    max_pos = int(cfg.get("max_positions") or 3)
    spread_pips = float(cfg.get("max_spread_pips") or 0.8)

    candidates: list[dict[str, Any]] = []
    if wr >= 80.0 and exp_r <= 0:
        candidates.append(
            {
                "id": "widen_tp_tharp",
                "weakness": "high_wr_neg_e",
                "patch": {"firehose_tp_pips": tp + 1},
                "rationale": "High WR with non-positive expectancy (Tharp): widen take-profit.",
            }
        )
        if "EURUSD" in {s.upper() for s in symbols}:
            dropped = [s for s in symbols if s.upper() != "EURUSD"]
            if dropped:
                candidates.append(
                    {
                        "id": "drop_eurusd_neg_e",
                        "weakness": "high_wr_neg_e",
                        "patch": {"symbols": dropped, "symbol": dropped[0]},
                        "rationale": "Hunt recorded EURUSD 95% WR with negative expectancy — drop it.",
                    }
                )
    if spread_skips >= 8:
        candidates.append(
            {
                "id": "tighten_spread_gate",
                "weakness": "spread_bleed",
                "patch": {"max_spread_pips": round(max(0.2, spread_pips * 0.8), 3)},
                "rationale": "spread_skip flood: tighten Harris max_spread_pips.",
            }
        )
    if consec_l >= 3 and 1 < max_pos < 40:
        candidates.append(
            {
                "id": "cut_max_positions",
                "weakness": "chop",
                "patch": {"max_positions": max(1, max_pos - 1)},
                "rationale": "Stacked losers / crowded book: cut max_positions.",
            }
        )
    if not bool(cfg.get("scratch_losers", False)) and float(cfg.get("max_hold_seconds") or 0) > 0:
        candidates.append(
            {
                "id": "scratch_losers_on",
                "weakness": "chop",
                "patch": {"scratch_losers": True},
                "rationale": "Enable scratch_losers so max-hold can exit underwater names.",
            }
        )
    # Always queue fallbacks. Rejected items still sit in `candidates`, so a
    # "if not candidates" probe never ran and the cycle stalled.
    if tp < 5:
        candidates.append(
            {
                "id": "widen_tp_probe",
                "weakness": "high_wr_neg_e",
                "patch": {"firehose_tp_pips": tp + 1},
                "rationale": "Default probe: slightly wider TP vs 30-pip SL (Tharp).",
            }
        )
    er_min = float(cfg.get("firehose_min_er") or 0.0)
    if er_min < 0.25:
        candidates.append(
            {
                "id": "kaufman_er_gate",
                "weakness": "chop",
                "patch": {"firehose_min_er": 0.3},
                "rationale": "Kaufman ER: skip the most inefficient / choppy bars.",
            }
        )
    dropped = [s for s in symbols if s.upper() != "GBPNZD"]
    if dropped and len(dropped) < len(symbols):
        candidates.append(
            {
                "id": "drop_gbpnzd_spread",
                "weakness": "spread_bleed",
                "patch": {"symbols": dropped, "symbol": dropped[0]},
                "rationale": "Journal spread_skips were GBPNZD; Harris: do not scalp fat spread.",
            }
        )
    if not bool(cfg.get("firehose_require_body", False)):
        candidates.append(
            {
                "id": "require_body_volman",
                "weakness": "chop",
                "patch": {"firehose_require_body": True},
                "rationale": "Volman: skip doji-like bars with no body so every-bar spray does not fill the book.",
            }
        )
    min_range = float(cfg.get("firehose_min_range_pips") or 0.0)
    if min_range < 1.0:
        candidates.append(
            {
                "id": "min_range_one_pip",
                "weakness": "chop",
                "patch": {"firehose_min_range_pips": 1.0},
                "rationale": "Firehose WR: skip dead bars so 3-pip takes are not fired into noise.",
            }
        )
    fat = {"EURNZD", "GBPNZD"}
    dropped_fat = [s for s in symbols if str(s).upper() not in fat]
    if dropped_fat and len(dropped_fat) < len(symbols):
        candidates.append(
            {
                "id": "drop_fat_nzd_crosses",
                "weakness": "spread_bleed",
                "patch": {"symbols": dropped_fat, "symbol": dropped_fat[0]},
                "rationale": "Harris on firehose: fat NZD crosses eat a 3-pip take — skip those names, keep 24h spray.",
            }
        )
    if tp > 1:
        nxt = tp - 1
        candidates.append(
            {
                "id": f"tighten_tp_to_{nxt}",
                "weakness": "chop",
                "patch": {"firehose_tp_pips": nxt},
                "rationale": (
                    f"Hunt high-WR firehose was 1-pip take (EURUSD sample 95.24% WR). "
                    f"Step TP {tp}->{nxt} on the same every-bar 24h spray."
                ),
            }
        )
    sl = int(cfg.get("firehose_sl_pips") or 30)
    if sl > 20:
        nxt_sl = sl - 5
        candidates.append(
            {
                "id": f"tighten_sl_to_{nxt_sl}",
                "weakness": "high_wr_neg_e",
                "patch": {"firehose_sl_pips": nxt_sl},
                "rationale": (
                    f"Tharp/Davey dollars on firehose: cut |avg_loss| SL {sl}->{nxt_sl} "
                    "without leaving every-bar 24h spray."
                ),
            }
        )
    cost_buf = float(cfg.get("cost_buffer") or 0.0)
    if cost_buf < 0.05:
        candidates.append(
            {
                "id": "cost_buffer_harris",
                "weakness": "spread_bleed",
                "patch": {"cost_buffer": 0.05},
                "rationale": "Harris/Aldridge: skip firehose bars where take does not clear cost_buffer after spread.",
            }
        )
    if min_range < 0.5:
        candidates.append(
            {
                "id": "min_range_half_pip",
                "weakness": "chop",
                "patch": {"firehose_min_range_pips": 0.5},
                "rationale": "Volman/Harris on firehose: skip sub-0.5-pip bars; 1-pip gate already failed OOS.",
            }
        )
    if cost_buf < 0.02:
        candidates.append(
            {
                "id": "cost_buffer_mild",
                "weakness": "spread_bleed",
                "patch": {"cost_buffer": 0.02},
                "rationale": (
                    "Harris/Aldridge on firehose: mild cost_buffer 0.02 so take must clear "
                    "spread+buffer; 0.05 already failed OOS."
                ),
            }
        )
    if er_min < 0.15:
        candidates.append(
            {
                "id": "kaufman_er_mild",
                "weakness": "chop",
                "patch": {"firehose_min_er": 0.15},
                "rationale": (
                    "Kaufman on firehose: mild ER 0.15 skips the deadest bars; "
                    "ER 0.3 already failed OOS. Keep every-bar 24h spray."
                ),
            }
        )
    if tp < 5:
        candidates.append(
            {
                "id": "widen_tp_to_5",
                "weakness": "high_wr_neg_e",
                "patch": {"firehose_tp_pips": 5},
                "rationale": (
                    "Tharp: exits dominate expectancy. Stored book_filter avg_win 0.088 vs "
                    "|avg_loss| 0.815; TP 4 was a noisy false accept. Probe TP 5 vs SL 25 "
                    "on the same every-bar 24h spray."
                ),
            }
        )
    if spread_pips > 0.70:
        candidates.append(
            {
                "id": "tighten_spread_mild",
                "weakness": "spread_bleed",
                "patch": {"max_spread_pips": 0.70},
                "rationale": (
                    "Harris/Aldridge: 0.64 spread gate starved OOS trades. Mild 0.70 vs "
                    "live 0.8 so a 3-pip take still clears cost without London-only."
                ),
            }
        )
    dropped_eu = [s for s in symbols if str(s).upper() != "EURUSD"]
    if dropped_eu and len(dropped_eu) < len(symbols):
        candidates.append(
            {
                "id": "drop_eurusd_hunt_e",
                "weakness": "high_wr_neg_e",
                "patch": {"symbols": dropped_eu, "symbol": dropped_eu[0]},
                "rationale": (
                    "Tharp/Davey: hunt EURUSD sample was 95.24% WR and lost dollars. "
                    "Drop that name; keep 24h firehose on the other pairs and max_positions 40."
                ),
            }
        )
    if float(cfg.get("flatten_if_profit_usd") or 0) <= 0:
        candidates.append(
            {
                "id": "lock_small_wins_tharp",
                "weakness": "high_wr_neg_e",
                "patch": {"flatten_if_profit_usd": 0.06},
                "rationale": (
                    "Tharp: exits dominate expectancy. Live avg_win ~0.07 vs open JPY "
                    "gives-back. Lock +$0.06 on the same 24h firehose; do not cut max_positions."
                ),
            }
        )
    if int(cfg.get("firehose_jpy_cluster_max") or 0) <= 0:
        candidates.append(
            {
                "id": "jpy_cluster_two_clenow",
                "weakness": "correlation_cluster",
                "patch": {"firehose_jpy_cluster_max": 2},
                "rationale": (
                    "Clenow/Davey: EURJPY+AUDJPY+CADJPY sells are one yen bet. Cap JPY "
                    "cluster at 2; keep max_positions 40 and 24h firehose on the other names."
                ),
            }
        )
    if float(cfg.get("max_hold_seconds") or 0) <= 0:
        candidates.append(
            {
                "id": "time_stop_30m_tharp",
                "weakness": "chop",
                "patch": {"max_hold_seconds": 1800},
                "rationale": (
                    "Tharp: exits dominate expectancy. 30-minute time stop frees stuck "
                    "0.01 clips on the same 24h firehose; do not cut max_positions."
                ),
            }
        )
    if not bool(cfg.get("firehose_vpa_filter", False)):
        candidates.append(
            {
                "id": "vpa_coulling_filter",
                "weakness": "chop",
                "patch": {"firehose_vpa_filter": True},
                "rationale": (
                    "Coulling VPA: skip absorption (high tick-volume, tiny range) and "
                    "low-volume wide bars. Tick volume is a proxy. Keep 24h firehose."
                ),
            }
        )
    if not bool(cfg.get("firehose_brooks_range", False)):
        candidates.append(
            {
                "id": "brooks_range_fade",
                "weakness": "chop",
                "patch": {"firehose_brooks_range": True},
                "rationale": (
                    "Brooks Ranges: in overlapping bars, skip the middle third; buy low "
                    "/ sell high. Do not cut max_positions or leave 24h firehose."
                ),
            }
        )
    if not bool(cfg.get("firehose_damir_structure", False)):
        candidates.append(
            {
                "id": "damir_structure_gate",
                "weakness": "chop",
                "patch": {"firehose_damir_structure": True},
                "rationale": (
                    "Damir 2016: do not buy LH/LL or sell HH/HL; skip excess against "
                    "value. Complementary to Brooks fade. Keep 24h firehose."
                ),
            }
        )
    if not bool(cfg.get("firehose_chart_read", False)):
        candidates.append(
            {
                "id": "nison_chart_read",
                "weakness": "chop",
                "patch": {"firehose_chart_read": True},
                "rationale": (
                    "Nison/Coulling: require candle/structure agreement on new firehose "
                    "entries. skip_doji/require_body already failed OOS; this is a "
                    "separate chart-read gate. Keep 24h firehose and max_positions 40."
                ),
            }
        )
    if not bool(cfg.get("firehose_jansen_filter", False)):
        candidates.append(
            {
                "id": "jansen_factor_score",
                "weakness": "chop",
                "patch": {"firehose_jansen_filter": True, "jansen_score_min": 0.15},
                "rationale": (
                    "Jansen 2018: trade the firehose side only when lagged momentum/RSI/ER "
                    "score agrees. Not a trained GBDT. Keep 24h firehose and max_positions 40."
                ),
            }
        )
    if not bool(cfg.get("firehose_harris_jump", False)):
        candidates.append(
            {
                "id": "harris_jump_censor",
                "weakness": "chop",
                "patch": {"firehose_harris_jump": True, "harris_jump_atr": 1.8},
                "rationale": (
                    "Harris: after an informed jump bar, do not chase that side (adverse "
                    "selection). Keep 24h firehose and max_positions 40."
                ),
            }
        )
    if not bool(cfg.get("oms_pretrade", False)):
        candidates.append(
            {
                "id": "donadio_oms_pretrade",
                "weakness": "chop",
                "patch": {"oms_pretrade": True, "max_quote_age_s": 5},
                "rationale": (
                    "Donadio HFT Ch.2/7: reject malformed/stale orders in the OMS before "
                    "they hit MT5; measure tick-to-trade. Not FPGA/C++. Keep 24h firehose."
                ),
            }
        )
    if not bool(cfg.get("firehose_no_stack_if_red", False)):
        candidates.append(
            {
                "id": "no_stack_into_red",
                "weakness": "chop",
                "patch": {"firehose_no_stack_if_red": True},
                "rationale": (
                    "Do not average down: skip another clip on a symbol whose open "
                    "tickets are already red. Keep 24h firehose and max_positions 40."
                ),
            }
        )
    if not bool(cfg.get("close_if_gave_back", False)):
        candidates.append(
            {
                "id": "giveback_lock_tharp",
                "weakness": "high_wr_neg_e",
                "patch": {
                    "close_if_gave_back": True,
                    "lock_mfe_usd": 0.04,
                    "giveback_floor_usd": 0.0,
                },
                "rationale": (
                    "Tharp/Brooks/Grimes: do not let a firehose scalp that was green "
                    "run to the 25-pip stop. Lock after +$0.04 MFE; close if it gives "
                    "back to $0. Keep 24h firehose and max_positions 40."
                ),
            }
        )
    if float(cfg.get("max_hold_seconds") or 0) <= 0:
        candidates.append(
            {
                "id": "time_stop_5m_volman",
                "weakness": "chop",
                "patch": {"max_hold_seconds": 300},
                "rationale": (
                    "Volman/Brooks scalp: 30-minute hold already failed OOS. Five-minute "
                    "time stop on the same 24h firehose so a 3-pip take cannot sit into "
                    "the 25-pip stop. Do not cut max_positions."
                ),
            }
        )
    if not bool(cfg.get("intel_enabled", False)) or not bool(cfg.get("intel_skip_rsi_ext", False)):
        candidates.append(
            {
                "id": "intel_rsi_ext_elder",
                "weakness": "impulse_censor",
                "patch": {"intel_enabled": True, "intel_skip_rsi_ext": True},
                "rationale": (
                    "Wilder/Elder around CORE: skip buy RSI>=70 and sell RSI<=30. "
                    "OOS E beat CORE on 8d EURUSD. Does not change 1/30."
                ),
            }
        )
    if int(cfg.get("intel_max_ema_streak") or 0) <= 0:
        candidates.append(
            {
                "id": "intel_ema_streak_12",
                "weakness": "impulse_censor",
                "patch": {
                    "intel_enabled": True,
                    "intel_max_ema_streak": 12,
                },
                "rationale": (
                    "Skip CORE when close has been on the same EMA side > 12 M1 bars. "
                    "Around-core only; keep 1/30 and max_positions 40."
                ),
            }
        )
    jan = float(cfg.get("jansen_score_min") or 0.0)
    if jan < 0.25:
        candidates.append(
            {
                "id": "jansen_score_025",
                "weakness": "chop",
                "patch": {"jansen_score_min": 0.25},
                "rationale": (
                    "Jansen: raise side-agreement min 0.15->0.25 around CORE. "
                    "Keep 1/30 and 24h firehose."
                ),
            }
        )
    names_upper = {str(s).upper() for s in symbols}
    if "NZDCHF" in names_upper:
        dropped_nc = [s for s in symbols if str(s).upper() != "NZDCHF"]
        if dropped_nc:
            candidates.append(
                {
                    "id": "drop_nzdchf_minlot",
                    "weakness": "spread_bleed",
                    "patch": {"symbols": dropped_nc, "symbol": dropped_nc[0]},
                    "rationale": (
                        "Live MT5 rejected NZDCHF 0.01 as below min lot 0.1. "
                        "Drop that name; do not raise size. Keep CORE 1/30."
                    ),
                }
            )
    if "NZDCAD" in names_upper:
        dropped_ncd = [s for s in symbols if str(s).upper() != "NZDCAD"]
        if dropped_ncd:
            candidates.append(
                {
                    "id": "drop_nzdcad_minlot",
                    "weakness": "spread_bleed",
                    "patch": {"symbols": dropped_ncd, "symbol": dropped_ncd[0]},
                    "rationale": (
                        "Live MT5 rejected NZDCAD 0.01 as below min lot 0.1. "
                        "Same as NZDCHF. Keep CORE 1/30 and max_positions 40."
                    ),
                }
            )
    if not bool(cfg.get("intel_skip_impulse_against", False)):
        candidates.append(
            {
                "id": "intel_impulse_against_elder",
                "weakness": "impulse_censor",
                "patch": {"intel_enabled": True, "intel_skip_impulse_against": True},
                "rationale": (
                    "Elder Impulse around CORE: skip buy on red impulse / sell on green. "
                    "Does not change 1/30."
                ),
            }
        )
    if float(cfg.get("lock_mfe_usd") or 0) >= 0.03:
        candidates.append(
            {
                "id": "lock_mfe_02_tharp",
                "weakness": "high_wr_neg_e",
                "patch": {"lock_mfe_usd": 0.02, "close_if_gave_back": True},
                "rationale": (
                    "Tharp/Brooks: lock after +$0.02 MFE so a 1-pip clip that was green "
                    "cannot sit into the 30-pip stop. Keep CORE TP/SL."
                ),
            }
        )
    if float(cfg.get("scratch_cooldown_s") or 0) < 60:
        candidates.append(
            {
                "id": "scratch_cooldown_2m",
                "weakness": "chop",
                "patch": {"scratch_cooldown_s": 120},
                "rationale": (
                    "Elder/Davey: after never-green or give-back, wait 2 minutes before "
                    "re-spraying that name. Stops the hydra. Keep CORE 1/30."
                ),
            }
        )
    if float(cfg.get("scratch_never_green_seconds") or 0) <= 0:
        candidates.append(
            {
                "id": "scratch_never_green_5m",
                "weakness": "high_wr_neg_e",
                "patch": {"scratch_never_green_seconds": 300},
                "rationale": (
                    "Grimes/Elder around CORE: if a 1-pip scalp never went green in 5 "
                    "minutes, scratch it. Do not sit into the 30-pip stop. Keep 1/30."
                ),
            }
        )
    if float(cfg.get("intel_quality_min") or 0) <= 0:
        candidates.append(
            {
                "id": "intel_quality_min_40",
                "weakness": "high_wr_neg_e",
                "patch": {"intel_enabled": True, "intel_quality_min": 40.0},
                "rationale": (
                    "Around CORE: skip bars with TradeQualityScore < 40. Extreme "
                    "buy-high/sell-low setups now cap at 28 (Brooks/Damir). "
                    "Does not change 1/30 or max_positions 40."
                ),
            }
        )
    if not bool(cfg.get("intel_skip_wrong_edge", False)):
        candidates.append(
            {
                "id": "intel_wrong_extreme_90",
                "weakness": "false_breakout",
                "patch": {
                    "intel_enabled": True,
                    "intel_skip_wrong_edge": True,
                    "intel_wrong_buy_loc": 0.90,
                    "intel_wrong_sell_loc": 0.10,
                },
                "rationale": (
                    "Brooks/Damir around CORE: reject buy loc>=0.90 / sell loc<=0.10 "
                    "in a range. Measured 30-pip stops were at that extreme."
                ),
            }
        )
    if not bool(cfg.get("intel_skip_weak_adx_edge", False)):
        candidates.append(
            {
                "id": "intel_weak_adx_edge",
                "weakness": "false_breakout",
                "patch": {
                    "intel_enabled": True,
                    "intel_skip_weak_adx_edge": True,
                    "intel_weak_adx": 22.0,
                },
                "rationale": (
                    "Wilder ADX<22 range plus Brooks/Damir floor/ceiling: skip CORE "
                    "spray only when the range is weak. Not full wrong_edge (lost OOS)."
                ),
            }
        )
    if not bool(cfg.get("intel_skip_extreme_doji", False)):
        candidates.append(
            {
                "id": "intel_unready_volman",
                "weakness": "chop",
                "patch": {
                    "intel_enabled": True,
                    "intel_skip_incomplete": True,
                    "intel_skip_extreme_doji": True,
                },
                "rationale": (
                    "Skip CORE when RSI/ADX/ER/range_loc are missing (warmup), or "
                    "Volman doji at loc>=0.90 buy / loc<=0.10 sell. No ADX cutoff."
                ),
            }
        )
    if not bool(cfg.get("intel_skip_floor_chop_sell", False)):
        candidates.append(
            {
                "id": "intel_floor_chop_sell",
                "weakness": "chop",
                "patch": {
                    "intel_enabled": True,
                    "intel_skip_floor_chop_sell": True,
                    "intel_floor_chop_er": 0.05,
                    "intel_floor_chop_loc": 0.15,
                },
                "rationale": (
                    "Kaufman/Damir around CORE: skip SELL only when ER<0.05 and "
                    "range_loc<=0.15. Not a global ER gate. Keep 1/30."
                ),
            }
        )
    core_tp_sl = (
        abs(float(cfg.get("firehose_tp_pips") or 0) - 1.0) < 1e-12
        and abs(float(cfg.get("firehose_sl_pips") or 0) - 30.0) < 1e-12
    )
    if core_tp_sl:
        candidates = [
            row
            for row in candidates
            if "firehose_tp_pips" not in (row.get("patch") or {})
            and "firehose_sl_pips" not in (row.get("patch") or {})
        ]
    blocked_keys = blocked_keys or set()
    for row in candidates:
        if str(row["id"]) in rejected:
            continue
        if patch_hits_frozen(row.get("patch"), blocked_keys):
            continue
        return row
    return None
