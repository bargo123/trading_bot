#!/usr/bin/env python3
"""Firehose book synthesis (Phase 2) + firehose_hypotheses.jsonl (Phase 15).

Reads the compiled knowledge base and classifies each source by relevance to
fast-turnover micro-edge trading. Produces:
  bot/reports/research/firehose_book_synthesis.json
  bot/reports/research/firehose_book_synthesis.md
  bot/knowledge/firehose_hypotheses.jsonl
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

KNOWLEDGE_DIR = BOT / "knowledge"

FAST_TURNOVER_TOPICS = {
    "scalping": ("scalp", "scalping", "small profit", "quick profit"),
    "microstructure": ("microstructure", "order flow", "bid-ask", "market making",
                       "inventory risk"),
    "spread": ("spread", "bid/ask", "transaction cost", "cost per trade",
               "commission"),
    "slippage": ("slippage", "fill quality", "execution quality"),
    "adverse_selection": ("adverse selection", "informed trader", "toxic flow"),
    "momentum": ("momentum", "impulse", "acceleration", "burst"),
    "mean_reversion": ("mean reversion", "reversion", "snap back", "fair value"),
    "breakout": ("breakout", "range break", "level break"),
    "failed_breakout": ("failed breakout", "false breakout", "trap"),
    "time_stop": ("time stop", "time-based exit", "holding period"),
    "noise": ("noise", "random", "choppy", "whipsaw"),
    "volatility_state": ("volatility expansion", "compression", "ATR",
                         "volatility regime"),
    "overtrading": ("overtrading", "too many trades", "trade frequency"),
    "validation": ("out-of-sample", "walk-forward", "backtest validation",
                   "overfitting"),
    "tail_loss": ("tail risk", "large loss", "risk of ruin", "drawdown control"),
}

RELEVANCE_KEYWORDS = set()
for kws in FAST_TURNOVER_TOPICS.values():
    RELEVANCE_KEYWORDS.update(kw.lower() for kw in kws)


def classify_source_relevance(records: list[dict]) -> tuple[str, list[str]]:
    """Classify one source as YES/PARTIAL/NO for fast-turnover relevance."""
    all_text = " ".join(
        r.get("passage_excerpt", "") + " " +
        ",".join(r.get("exit_categories") or [])
        for r in records
    ).lower()
    matched = [topic for topic, kws in FAST_TURNOVER_TOPICS.items()
               if any(kw.lower() in all_text for kw in kws)]
    if len(matched) >= 4:
        return "YES", matched
    if len(matched) >= 1:
        return "PARTIAL", matched
    return "NO", []


def main() -> int:
    manifest_path = KNOWLEDGE_DIR / "corpus_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("ERROR: knowledge base not built")
        return 1

    # Load all records.
    all_records: dict[str, list[dict]] = {}  # file -> records
    for rec_file in sorted(KNOWLEDGE_DIR.glob("*.jsonl")):
        for line in rec_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            loc = rec.get("location", {})
            file_key = loc.get("file") or "?"
            all_records.setdefault(file_key, []).append(rec)

    synthesis: list[dict] = []
    firehose_hypotheses: list[dict] = []

    for finfo in manifest.get("files", []):
        fname = finfo.get("file", "")
        short_name = fname.split("/")[-1].replace(".md", "")
        records = all_records.get(fname, [])
        relevant, topics_matched = classify_source_relevance(records)

        entry_hyps = [r for r in records if r.get("concept_type") == "ENTRY_PRINCIPLE"]
        exit_hyps = [r for r in records if r.get("concept_type") == "EXIT_PRINCIPLE"]
        strat_hyps = [r for r in records if r.get("concept_type") == "STRATEGY_HYPOTHESIS"]
        risk_hyps = [r for r in records if r.get("concept_type") == "RISK_PRINCIPLE"]
        exec_hyps = [r for r in records if r.get("concept_type") == "EXECUTION_PRINCIPLE"]

        source_entry = {
            "source": short_name,
            "file": fname,
            "file_hash": finfo.get("file_hash", ""),
            "status": finfo.get("status", "?"),
            "relevant_to_fast_turnover": relevant,
            "topics_matched": topics_matched,
            "record_counts": {
                "entry": len(entry_hyps),
                "exit": len(exit_hyps),
                "strategy": len(strat_hyps),
                "risk": len(risk_hyps),
                "execution": len(exec_hyps),
                "total": len(records),
            },
            "passage_hashes": [r.get("passage_hash") for r in records[:10]],
        }
        synthesis.append(source_entry)

        # Extract executable fast-turnover hypotheses.
        for hyp in strat_hyps:
            if not hyp.get("executable"):
                continue
            fh_hyp = {
                "firehose_hypothesis_id": f"ftfb_{hyp['passage_hash'][:16]}",
                "source_books": [hyp.get("book")],
                "source_hashes": [finfo.get("file_hash")],
                "passage_hashes": [hyp.get("passage_hash")],
                "family": hyp.get("strategy_family") or "",
                "mechanism": hyp.get("mechanism") or "",
                "context_timeframe": "M15/M5",
                "execution_timeframe": "M1/tick",
                "side_rule": hyp.get("side_rule") or "",
                "entry_trigger": hyp.get("entry_hypothesis") or "",
                "confirmation": "",
                "invalidation": hyp.get("invalidation_hypothesis") or "",
                "exit": hyp.get("exit_hypothesis") or "",
                "expected_hold_horizon_s": 120,
                "cost_constraints": f"spread_p75+slippage from cost_profiles.json",
                "spread_constraints": "< p90 for symbol/session",
                "regime": hyp.get("required_regime") or "",
                "session_constraints": "",
                "required_data": "completed M1 bars + M15 structure + live quote",
                "falsification": hyp.get("falsification_condition") or "",
                "known_failure_modes": ["adverse selection", "spread widening",
                                        "whipsaw on low timeframe"],
                "status": "PROPOSED",
            }
            firehose_hypotheses.append(fh_hyp)

    out_dir = BOT / "reports" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)

    report_json = {
        "schema": "firehose_book_synthesis.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "corpus_version": manifest.get("corpus_version"),
        "sources_total": len(synthesis),
        "relevant_yes": sum(1 for s in synthesis if s["relevant_to_fast_turnover"] == "YES"),
        "relevant_partial": sum(1 for s in synthesis if s["relevant_to_fast_turnover"] == "PARTIAL"),
        "relevant_no": sum(1 for s in synthesis if s["relevant_to_fast_turnover"] == "NO"),
        "executable_firehose_hypotheses": len(firehose_hypotheses),
        "sources": synthesis,
    }
    (out_dir / "firehose_book_synthesis.json").write_text(
        json.dumps(report_json, indent=2), encoding="utf-8")

    md_lines = [
        "# Firehose Book Synthesis",
        f"_Generated {report_json['generated_utc']}_",
        f"- Corpus version: `{manifest.get('corpus_version', '')[:16]}`",
        f"- Sources: {report_json['sources_total']} "
        f"(YES={report_json['relevant_yes']} PARTIAL={report_json['relevant_partial']} "
        f"NO={report_json['relevant_no']})",
        f"- Executable firehose hypotheses: {len(firehose_hypotheses)}",
        "",
        "| Source | Relevant | Topics | Entry | Exit | Strategy | Risk | Exec |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in synthesis:
        rc = s["record_counts"]
        md_lines.append(
            f"| {s['source'][:35]} | {s['relevant_to_fast_turnover']} "
            f"| {','.join(s['topics_matched'][:3])} "
            f"| {rc['entry']} | {rc['exit']} | {rc['strategy']} "
            f"| {rc['risk']} | {rc['execution']} |"
        )
    (out_dir / "firehose_book_synthesis.md").write_text("\n".join(md_lines), encoding="utf-8")

    # Write firehose_hypotheses.jsonl.
    hyp_path = BOT / "knowledge" / "firehose_hypotheses.jsonl"
    with hyp_path.open("w", encoding="utf-8") as fh:
        for h in firehose_hypotheses:
            fh.write(json.dumps(h, sort_keys=True) + "\n")

    print(json.dumps({
        "synthesis_md": str(out_dir / "firehose_book_synthesis.md"),
        "hypotheses_jsonl": str(hyp_path),
        "sources": report_json["sources_total"],
        "relevant_yes_partial_no": [
            report_json["relevant_yes"], report_json["relevant_partial"],
            report_json["relevant_no"]],
        "executable_firehose_hypotheses": len(firehose_hypotheses),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
