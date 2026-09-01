#!/usr/bin/env python3
"""OLD firehose vs INTELLIGENT firehose economics, from the real demo journals.

Aggregates in Python rather than reasoning over 45 MB of JSONL. Every number here
comes from bot/reports/*.jsonl written by run_broker_paper.py.

The report deliberately leads with payoff structure, not win rate: the reference
failure was WR 91.91% with PF 0.71, so a win-rate improvement is not evidence of
anything. It also does NOT credit the intelligent path for trading less - fewer
trades at the same expectancy is not an improvement.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bot"))

from aegis.intel.expected_value import payoff_metrics  # noqa: E402

# The reported regression this work exists to fix.
REFERENCE_FAILURE = {
    "label": "MT5 report (reference failure)",
    "trades": 1175,
    "wins": 1080,
    "win_rate": 1080 / 1175,
    "gross_profit": 26.33,
    "gross_loss": -37.09,
    "net": -10.71,
    "profit_factor": 26.33 / 37.09,
}


def _rows(path: Path):
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def analyse(path: Path) -> dict:
    """Split a journal into CORE-attributed and brain-attributed closed P/L."""
    actions: Counter = Counter()
    events: Counter = Counter()
    skip_reasons: Counter = Counter()
    econ_reasons: Counter = Counter()
    brain_pnl: list[float] = []
    other_pnl: list[float] = []
    econ_seen = 0
    size_seen = 0
    provenance: Counter = Counter()

    for row in _rows(path):
        event = str(row.get("event") or "")
        events[event] += 1
        action = row.get("action")
        if action:
            actions[str(action)] += 1
        if action in {"skip", "hold"} and row.get("reason"):
            skip_reasons[str(row["reason"])] += 1
        if "econ_reason" in row:
            econ_seen += 1
            econ_reasons[str(row.get("econ_reason"))] += 1
        if "size_reason" in row:
            size_seen += 1
        if "analogue_provenance" in row:
            provenance[str(row["analogue_provenance"])] += 1
        pnl = row.get("pnl")
        if isinstance(pnl, (int, float)):
            if str(event).startswith("intel_brain_"):
                brain_pnl.append(float(pnl))
            else:
                other_pnl.append(float(pnl))

    return {
        "path": str(path.relative_to(REPO)).replace("\\", "/"),
        "bytes": path.stat().st_size,
        "events": dict(events.most_common(12)),
        "actions": dict(actions),
        "top_skip_reasons": dict(skip_reasons.most_common(12)),
        "econ_records": econ_seen,
        "econ_reasons": dict(econ_reasons.most_common(12)),
        "size_records": size_seen,
        "analogue_provenance": dict(provenance),
        "brain_exit_payoff": payoff_metrics(brain_pnl),
        "other_close_payoff": payoff_metrics(other_pnl),
        "all_payoff": payoff_metrics(brain_pnl + other_pnl),
    }


def _fmt(value, spec: str = ".4f") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return format(value, spec)
    return str(value)


def _payoff_table(title: str, stats: dict) -> list[str]:
    return [
        f"### {title}",
        "",
        "| metric | value |",
        "| --- | --- |",
        f"| trades (closed P/L observations) | {stats['n']} |",
        f"| wins / losses | {stats['n_wins']} / {stats['n_losses']} |",
        f"| win rate | {_fmt(stats['win_rate'], '.2%')} |",
        f"| **expectancy / trade** | **{_fmt(stats['expectancy'])}** |",
        f"| **profit factor** | **{_fmt(stats['profit_factor'], '.3f')}** |",
        f"| avg win | {_fmt(stats['avg_win'])} |",
        f"| avg loss | {_fmt(stats['avg_loss'])} |",
        f"| payoff ratio | {_fmt(stats['payoff_ratio'], '.3f')} |",
        f"| breakeven WR required | {_fmt(stats['breakeven_wr'], '.2%')} |",
        f"| wins erased by avg loss | {_fmt(stats['wins_erased_by_average_loss'], '.2f')} |",
        f"| wins erased by tail loss | {_fmt(stats['wins_erased_by_tail_loss'], '.2f')} |",
        f"| tail loss | {_fmt(stats['tail_loss'])} |",
        f"| net P/L | {_fmt(stats['net_pnl'], '.2f')} |",
        f"| cosmetic win rate? | {stats['cosmetic_win_rate']} |",
        "",
    ]


def main() -> int:
    journals = [
        path
        for path in sorted((REPO / "bot" / "reports").rglob("*.jsonl"))
        if path.stat().st_size > 1000
    ]
    results = [analyse(path) for path in journals]

    out_dir = REPO / "bot" / "reports" / "claude"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "firehose_comparison.json").write_text(
        json.dumps({"reference_failure": REFERENCE_FAILURE, "journals": results}, indent=2, default=str),
        encoding="utf-8",
    )

    ref = REFERENCE_FAILURE
    lines = [
        "# OLD firehose vs INTELLIGENT firehose",
        "",
        "All figures are computed from the committed demo journals by",
        "`bot/scripts/claude_firehose_comparison.py`. Win rate is reported but is",
        "never the verdict: the reference failure had a 91.91% win rate and still lost",
        "money. A lower trade count is likewise not counted as an improvement.",
        "",
        "## Reference failure (the target to beat)",
        "",
        "| metric | value |",
        "| --- | --- |",
        f"| trades | {ref['trades']} |",
        f"| win rate | {ref['win_rate']:.2%} |",
        f"| gross profit | ${ref['gross_profit']:.2f} |",
        f"| gross loss | ${ref['gross_loss']:.2f} |",
        f"| net | ${ref['net']:.2f} |",
        f"| profit factor | {ref['profit_factor']:.3f} |",
        "",
        "A 91.91% win rate with PF 0.71 means the average loss erased roughly 30",
        "average wins. Raising the win rate cannot fix that; only payoff structure can.",
        "",
        "## Journals found",
        "",
        "| journal | bytes | fire | scale | hold | reduce | exit | skip |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for res in results:
        acts = res["actions"]
        lines.append(
            f"| `{res['path']}` | {res['bytes']:,} | {acts.get('fire', 0)} | "
            f"{acts.get('scale', 0)} | {acts.get('hold', 0)} | {acts.get('reduce', 0)} | "
            f"{acts.get('exit', 0)} | {acts.get('skip', 0)} |"
        )
    lines.append("")

    for res in results:
        if res["all_payoff"]["n"] == 0:
            continue
        lines += [f"## `{res['path']}`", ""]
        if res["analogue_provenance"]:
            lines += [
                f"Analogue provenance seen in this run: `{res['analogue_provenance']}`",
                "",
            ]
        if res["econ_records"]:
            lines += [
                f"Per-trade economics records: {res['econ_records']}, "
                f"sizing records: {res['size_records']}",
                "",
                f"Economics verdicts: `{res['econ_reasons']}`",
                "",
            ]
        else:
            lines += [
                "_No per-trade economics fields in this journal: it predates the EV gate._",
                "",
            ]
        lines += _payoff_table("All closed P/L", res["all_payoff"])
        if res["brain_exit_payoff"]["n"]:
            lines += _payoff_table("Intelligent-brain exits only", res["brain_exit_payoff"])
        if res["other_close_payoff"]["n"]:
            lines += _payoff_table("CORE / other closes", res["other_close_payoff"])
        if res["top_skip_reasons"]:
            lines += ["Top skip/hold reasons:", "", "```", json.dumps(res["top_skip_reasons"], indent=2), "```", ""]

    (out_dir / "firehose_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=== summary ===")
    for res in results:
        stats = res["all_payoff"]
        if stats["n"] == 0:
            print(f"{res['path']}: no closed P/L")
            continue
        print(
            f"{res['path']}: n={stats['n']} wr={_fmt(stats['win_rate'], '.2%')} "
            f"pf={_fmt(stats['profit_factor'], '.3f')} exp={_fmt(stats['expectancy'])} "
            f"payoff={_fmt(stats['payoff_ratio'], '.3f')} net={_fmt(stats['net_pnl'], '.2f')} "
            f"econ_records={res['econ_records']}"
        )
    print(f"\nwrote {(out_dir / 'firehose_comparison.md').relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
