"""Generated research reports. Read-only versus the live runner."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aegis.research.capabilities import RESEARCH_PROXY, UNAVAILABLE
from aegis.research.ingest import ingest_live_state
from aegis.research.modules import IMPLEMENTED, MODULE_LABELS
from aegis.research.source_notes import MISSING_EXTRACTS


def capability_matrix() -> list[dict[str, Any]]:
    rows = []
    seen: set[str] = set()
    for name, available in UNAVAILABLE.items():
        rows.append(
            {
                "capability": name,
                "status": "implemented" if available else "unavailable",
                "proof": "aegis.research.capabilities.UNAVAILABLE",
            }
        )
        seen.add(name)
    for name, available in RESEARCH_PROXY.items():
        if name in seen:
            continue
        rows.append(
            {
                "capability": name,
                "status": "research_proxy" if available else "unavailable",
                "proof": "aegis.research.capabilities.RESEARCH_PROXY",
            }
        )
        seen.add(name)
    for name, label in MODULE_LABELS.items():
        if name in seen:
            continue
        proof = IMPLEMENTED.get(name, "")
        if name == "harris_jump_live" and not proof:
            proof = "aegis.research.harris.jump_is_local_heuristic"
        rows.append({"capability": name, "status": label, "proof": proof})
        seen.add(name)
    rows.append({"capability": "tick_store", "status": "implemented", "proof": "aegis.research.store.TickStore"})
    rows.append({"capability": "broker_tz_bars", "status": "implemented", "proof": "aegis.research.bars"})
    rows.append({"capability": "vap_tap_proxy", "status": "research_proxy", "proof": "aegis.research.profile"})
    rows.append(
        {
            "capability": "news_blackout_gate",
            "status": "implemented",
            "proof": "aegis.research.news.in_blackout (offline PIT calendar file; fails closed)",
        }
    )
    return rows


def book_compliance_matrix() -> list[dict[str, str]]:
    rows = [
        {"book": "Coulling VPA", "implemented": "tick-volume effort proxy", "gap": "not centralized volume", "claim": "must not call true VPA"},
        {"book": "Brooks Ranges", "implemented": "5m location/failed-break proxy", "gap": "not the full 3-book method", "claim": "must not call faithful Brooks"},
        {"book": "Damir 2016", "implemented": "H4/M15 retest proxy", "gap": "not M1-only", "claim": "must not call full Damir"},
        {"book": "Jansen ML", "implemented": "none", "gap": "no trained PIT model", "claim": "jansen_score is a heuristic"},
        {"book": "Harris", "implemented": "spread-vs-take constraint + event blackout gate", "gap": "no L2/queue", "claim": "harris_jump is local heuristic"},
        {"book": "Steidlmayer", "implemented": "TPO time-at-price proxy", "gap": "not pit IB", "claim": "must not call Market Profile pit"},
        {"book": "Chan 2013", "implemented": "chan_bb_fade research entry + chan_bb_scalp demo algo", "gap": "extract on disk; costs kill naive MR", "claim": "research_proxy not faithful Chan basket"},
        {"book": "Prado AFML", "implemented": "purged_holdout + meta-label + triple-barrier + CPCV proxy", "gap": "extract on disk; no full AFML library or LOB features", "claim": "research_proxy not Jansen ML"},
        {"book": "Frost/Prechter Elliott", "implemented": "objective swing-leg counter", "gap": "OCR extract on disk; subjective wave counts rejected by Aronson", "claim": "research_proxy not Elliott Wave Principle"},
        {"book": "Johnson DMA", "implemented": "spread-vs-ATR gate only", "gap": "OCR extract on disk; no exchange DMA/co-lo", "claim": "research_proxy; DMA unavailable on retail MT5"},
        {"book": "Gann 1976", "implemented": "bar-count cycle + slope/ATR proxy", "gap": "OCR extract on disk; not hand-drawn angles", "claim": "research_proxy"},
        {"book": "Zuckerman Medallion", "implemented": "six_book_stack vote ensemble + overfit gates", "gap": "narrative not a strategy book", "claim": "research_proxy; no Medallion replication"},
        {"book": "Nison / du Plessis", "implemented": "PnF/Renko/Kagi/TLB engines", "gap": "research_proxy", "claim": "not a trading system"},
    ]
    named_already = {
        "johnson",
        "frost_prechter",
        "gann",
        "chan_2013",
        "prado",
        "zuckerman",
    }
    for key, why in MISSING_EXTRACTS.items():
        if key in named_already:
            continue
        rows.append({"book": key, "implemented": "none", "gap": why, "claim": "unavailable extract"})
    return rows


def write_reports(
    out_dir: Path,
    *,
    heartbeat_path: Path,
    risk_path: Path,
    champion: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
    last_decision: dict[str, Any] | None,
    journal_path: Path | None = None,
    deals_path: Path | None = None,
) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    live = ingest_live_state(
        heartbeat_path=heartbeat_path,
        risk_path=risk_path,
        journal_path=journal_path,
        deals_path=deals_path,
    )
    cap_path = out_dir / "capability_matrix.md"
    cap_path.write_text(_table("# Capability matrix", capability_matrix()), encoding="utf-8")
    book_path = out_dir / "book_compliance.md"
    book_path.write_text(_table("# Book-compliance matrix", book_compliance_matrix()), encoding="utf-8")
    champ_path = out_dir / "current_best.md"
    if champion is None:
        champ_body = (
            "# Current best verified research candidate\n\n"
            "None. No challenger has passed costed holdout expectancy, profit factor, "
            "and search-count gates on real MT5 data.\n"
        )
        if baseline:
            champ_body += (
                f"\nFirehose benchmark `{baseline.get('name')}`: "
                f"trades={baseline.get('total_trades')} E={baseline.get('expectancy_r')} "
                f"PF={baseline.get('profit_factor')} (not a champion).\n"
            )
    else:
        champ_body = f"# Current best\n\n`{champion.get('id')}` E={champion.get('expectancy')}\n"
    champ_path.write_text(champ_body, encoding="utf-8")
    lvm_path = out_dir / "live_vs_model.md"
    obs = live.get("observed") or {}
    lvm_body = (
        "# Live versus model\n\n"
        f"Live equity={live.get('equity')} open={live.get('open')} halted={live.get('risk_halted')}.\n\n"
        "## Observed demo (journal / deals)\n\n"
        f"- orders ok/fail: {obs.get('journal_ok')}/{obs.get('journal_fail')} "
        f"(10019={obs.get('journal_10019')}, spread_skip={obs.get('journal_spread_skips')})\n"
        f"- flatten clips (Phase 0 sealed): n={obs.get('flatten_n')} WR={obs.get('flatten_wr')} "
        f"E={obs.get('flatten_e')} PF={obs.get('flatten_pf')}\n"
        f"- deals Phase 0 sealed: n={obs.get('phase0_deals_n')} WR={obs.get('phase0_deals_wr')} "
        f"E={obs.get('phase0_deals_e')} PF={obs.get('phase0_deals_pf')} net={obs.get('phase0_deals_net')}\n"
        f"- deals ticket-deduped ingest: n={obs.get('deals_n')} WR={obs.get('deals_wr')} "
        f"E={obs.get('deals_e')} PF={obs.get('deals_pf')} net={obs.get('deals_net')}"
        f" (raw={obs.get('deals_n_raw')}, deduped_by={obs.get('deals_deduped_by', 'phase0')})\n"
        f"- source: {obs.get('source')}\n\n"
    )
    if baseline:
        lvm_body += (
            "## Named firehose benchmark (not the same window unless labeled)\n\n"
            f"- `{baseline.get('name')}` trades={baseline.get('total_trades')} "
            f"E={baseline.get('expectancy_r')} PF={baseline.get('profit_factor')} "
            f"not_a_champion={baseline.get('not_a_champion', True)}\n"
        )
    else:
        lvm_body += (
            "## Same-window model replay\n\n"
            "Not attached. Do not treat old optimizer synthetic accepts as live-valid.\n"
        )
    lvm_path.write_text(lvm_body, encoding="utf-8")
    safety_path = out_dir / "safety_dashboard.md"
    safety_path.write_text(
        "# Safety dashboard\n\n"
        f"- risk_halted: {live.get('risk_halted')} ({live.get('risk_reason')})\n"
        f"- permanent_halt: {live.get('permanent_halt')}\n"
        f"- circuit_ok: {live.get('circuit_ok')}\n"
        f"- quote_stale: {live.get('quote_stale')}\n"
        f"- open: {live.get('open')} {live.get('held')}\n"
        f"- last_decision: {(last_decision or {}).get('decision', 'none')}\n"
        f"- live YAML writable: {live.get('live_yaml_writable')}\n",
        encoding="utf-8",
    )
    return {
        "capability": cap_path,
        "books": book_path,
        "champion": champ_path,
        "live_vs_model": lvm_path,
        "safety": safety_path,
    }


def _table(title: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return title + "\n\n(empty)\n"
    keys = list(rows[0].keys())
    lines = [title, "", "| " + " | ".join(keys) + " |", "| " + " | ".join("---" for _ in keys) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(k, "")) for k in keys) + " |")
    return "\n".join(lines) + "\n"
