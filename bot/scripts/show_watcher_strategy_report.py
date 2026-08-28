#!/usr/bin/env python3
"""Render Watcher-only outcomes for every book-derived strategy record."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        return
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    yield value
    except OSError:
        return


def _text(value: Any) -> str:
    return str(value or "").strip()


def _empty_strategy(record: Mapping[str, Any]) -> dict[str, Any]:
    raw = record.get("raw_record") if isinstance(record.get("raw_record"), Mapping) else {}
    provenance = record.get("provenance") if isinstance(record.get("provenance"), Mapping) else {}
    source_status = _text(raw.get("status") or record.get("validation_status")).upper() or "LEGACY_UNCOMPILED"
    return {
        "record_id": record.get("record_id"),
        "book": provenance.get("book") or raw.get("book") or raw.get("source_title"),
        "book_hash": provenance.get("book_hash") or raw.get("file_hash") or raw.get("source_hash"),
        "source_file": record.get("source_file"),
        "source_line": record.get("source_line"),
        "strategy_family": raw.get("strategy_family") or raw.get("concept"),
        "side_rule": raw.get("side_rule"),
        "validation_status": record.get("validation_status"),
        "testability": record.get("testability"),
        "evidence_status": source_status,
        "evidence_source": "UNAVAILABLE",
        "opinion_counts": {"BUY": 0, "SELL": 0, "NO_TRADE": 0, "NOT_APPLICABLE": 0},
        "evaluated_decisions": 0,
        "applicable_decisions": 0,
        "shadow_trades": 0,
        "shadow_closed": 0,
        "confirmed_outcomes": 0,
        "broker_sample_size": 0,
        "broker_wins": 0,
        "broker_losses": 0,
        "broker_net_win_rate": None,
        "broker_net_win_rate_percent": None,
        "exact_sample_size": 0,
        "exact_win_rate": None,
        "exact_win_rate_percent": None,
        "proxy_sample_size": 0,
        "proxy_win_rate": None,
        "proxy_win_rate_percent": None,
        "unattributed_outcomes": 0,
        "wins": 0,
        "losses": 0,
        "net_pnl_usd": None,
        "shadow_net_pnl_usd": None,
        "confirmed_net_pnl_usd": None,
        "positive_pnl_usd": 0.0,
        "negative_pnl_usd": 0.0,
        "status": "NOT_OBSERVED",
    }


def _add_result(row: dict[str, Any], net: Any, *, source: str) -> None:
    value = _number(net)
    if value is None:
        return
    row["net_pnl_usd"] = (row["net_pnl_usd"] or 0.0) + value
    source_key = f"{source}_net_pnl_usd"
    row[source_key] = (row[source_key] or 0.0) + value
    row[f"{source}_wins"] = int(row.get(f"{source}_wins") or 0) + int(value > 0)
    row[f"{source}_losses"] = int(row.get(f"{source}_losses") or 0) + int(value < 0)
    if value > 0:
        row["wins"] += 1
        row["positive_pnl_usd"] += value
    elif value < 0:
        row["losses"] += 1
        row["negative_pnl_usd"] += value
    if source == "confirmed":
        row["broker_sample_size"] += 1
        row["broker_wins"] += int(value > 0)
        row["broker_losses"] += int(value < 0)


def build_strategy_report(report_dir: Path) -> dict[str, Any]:
    """Rebuild a strategy/book outcome view from Watcher reports only."""
    root = Path(report_dir)
    library = _json(root / "knowledge_library.json", {})
    records = library.get("records") if isinstance(library, Mapping) else []
    records = [row for row in records if isinstance(row, Mapping) and row.get("category") == "strategy"]
    strategies = {str(row.get("record_id")): _empty_strategy(row) for row in records if row.get("record_id")}
    stats_payload = _json(root / "strategy_stats.json", {})
    per_strategy = stats_payload.get("per_strategy") if isinstance(stats_payload, Mapping) else {}
    if isinstance(per_strategy, Mapping) and per_strategy:
        for key, observation in per_strategy.items():
            row = strategies.get(str(key))
            if row is None or not isinstance(observation, Mapping):
                continue
            row["evaluated_decisions"] = int(observation.get("evaluated_decisions") or 0)
            row["applicable_decisions"] = int(observation.get("applicable_decisions") or 0)
            row["evidence_status"] = _text(observation.get("evidence_status")) or row["evidence_status"]
            counts = observation.get("opinion_counts")
            if isinstance(counts, Mapping):
                for label in row["opinion_counts"]:
                    row["opinion_counts"][label] = int(counts.get(label) or 0)
    else:
        # Compatibility for small fixtures/older reports.  The live engine now
        # persists aggregates, so this branch never scans a multi-gigabyte log.
        analysis_path = root / "decision_analysis.jsonl"
        try:
            small_enough = analysis_path.stat().st_size <= 50_000_000
        except OSError:
            small_enough = False
        if small_enough:
            for analysis in _iter_jsonl(analysis_path):
                for opinion in analysis.get("strategy_opinions") or []:
                    if not isinstance(opinion, Mapping):
                        continue
                    key = _text(opinion.get("record_id"))
                    row = strategies.get(key)
                    if row is None:
                        continue
                    row["evaluated_decisions"] += 1
                    label = _text(opinion.get("opinion")).upper()
                    if label in row["opinion_counts"]:
                        row["opinion_counts"][label] += 1
                    if _text(opinion.get("applicability_status")).upper() == "APPLICABLE":
                        row["applicable_decisions"] += 1

    latest_shadow: dict[str, Mapping[str, Any]] = {}
    for shadow in _iter_jsonl(root / "shadow_trades.jsonl"):
        shadow_id = _text(shadow.get("shadow_id"))
        if shadow_id:
            latest_shadow[shadow_id] = shadow
    for shadow in latest_shadow.values():
        ids = [str(value) for value in shadow.get("strategy_ids") or [] if value]
        for key in ids:
            row = strategies.get(key)
            if row is None:
                continue
            row["shadow_trades"] += 1
            if _text(shadow.get("shadow_status")).upper() == "CLOSED":
                row["shadow_closed"] += 1
                _add_result(row, shadow.get("net_pnl_usd"), source="shadow")

    seen_outcomes: set[str] = set()
    unlinked_confirmed = 0
    for outcome in _iter_jsonl(root / "outcomes.jsonl"):
        if not outcome.get("broker_confirmed"):
            continue
        outcome_id = _text(outcome.get("outcome_id"))
        if outcome_id and outcome_id in seen_outcomes:
            continue
        if outcome_id:
            seen_outcomes.add(outcome_id)
        features = outcome.get("features") if isinstance(outcome.get("features"), Mapping) else {}
        ids = features.get("strategy_ids") or features.get("strategy_id") or features.get("strategy_record_id") or features.get("hypothesis_id")
        if isinstance(ids, str):
            ids = [ids]
        ids = [str(value) for value in ids or [] if value]
        linked = False
        for key in ids:
            row = strategies.get(key)
            if row is None:
                continue
            linked = True
            row["confirmed_outcomes"] += 1
            _add_result(row, outcome.get("realized_net_usd"), source="confirmed")
        if not linked:
            unlinked_confirmed += 1

    for row in strategies.values():
        if row["confirmed_outcomes"]:
            row["status"] = "OBSERVED_BROKER"
        elif row["shadow_closed"]:
            row["status"] = "OBSERVED_SHADOW"
        elif row["applicable_decisions"]:
            row["status"] = "APPLICABLE_UNREPLAYED"
        elif row["evaluated_decisions"]:
            row["status"] = "EVALUATED_NOT_APPLICABLE"
        if row["wins"] + row["losses"]:
            row["win_rate"] = row["wins"] / (row["wins"] + row["losses"])
        else:
            row["win_rate"] = None
        if row["losses"] and row["wins"]:
            row["profit_factor"] = row["positive_pnl_usd"] / abs(row["negative_pnl_usd"])
        else:
            row["profit_factor"] = None
        if row["broker_sample_size"]:
            row["broker_net_win_rate"] = row["broker_wins"] / row["broker_sample_size"]
            row["broker_net_win_rate_percent"] = row["broker_net_win_rate"] * 100.0
            if row["evidence_status"] == "CODED_EXACT":
                row["exact_sample_size"] = row["broker_sample_size"]
                row["exact_win_rate"] = row["broker_net_win_rate"]
                row["exact_win_rate_percent"] = row["broker_net_win_rate_percent"]
                row["evidence_status"] = "EXACT_MEASURED"
                row["evidence_source"] = "broker_confirmed_net_pnl"
            else:
                row["evidence_source"] = "broker_confirmed_net_pnl_unclassified"
        if row.get("shadow_closed"):
            shadow_wins = int(row.get("shadow_wins") or 0)
            shadow_losses = int(row.get("shadow_losses") or 0)
            row["proxy_sample_size"] = shadow_wins + shadow_losses
            if row["proxy_sample_size"]:
                row["proxy_win_rate"] = shadow_wins / row["proxy_sample_size"]
                row["proxy_win_rate_percent"] = row["proxy_win_rate"] * 100.0
            if row["evidence_status"] in {"LEGACY_UNCOMPILED", "CODED_EXACT"} and not row["broker_sample_size"]:
                row["evidence_status"] = "FAMILY_PROXY"
                row["evidence_source"] = "shadow_replay_proxy"
        if row["evidence_status"] == "CODED_EXACT" and not row["broker_sample_size"]:
            row["evidence_status"] = "CODED_EXACT_NO_SAMPLES"
            row["evidence_source"] = "UNAVAILABLE"
        elif row["evidence_status"] in {"UNTESTABLE_SOURCE", "COMPILE_ERROR", "FAMILY_PROXY"} and not row["broker_sample_size"] and not row.get("shadow_closed"):
            row["evidence_source"] = row["evidence_status"]

    books: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "book": None,
        "strategies": 0,
        "applicable_decisions": 0,
        "shadow_closed": 0,
        "confirmed_outcomes": 0,
        "wins": 0,
        "losses": 0,
        "net_pnl_usd": 0.0,
    })
    for row in strategies.values():
        book = _text(row.get("book")) or "UNKNOWN"
        summary = books[book]
        summary["book"] = book
        summary["strategies"] += 1
        for field in ("applicable_decisions", "shadow_closed", "confirmed_outcomes", "wins", "losses"):
            summary[field] += row[field]
        if row["net_pnl_usd"] is not None:
            summary["net_pnl_usd"] += row["net_pnl_usd"]
    ordered = sorted(strategies.values(), key=lambda row: (
        -row["confirmed_outcomes"], -row["shadow_closed"], -row["applicable_decisions"], str(row["record_id"])
    ))
    return {
        "schema": "watcher_strategy_outcome_report.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "corpus_version": library.get("corpus_version"),
        "total_strategies": len(ordered),
        "observed_strategies": sum(row["status"].startswith("OBSERVED") for row in ordered),
        "applicable_unreplayed": sum(row["status"] == "APPLICABLE_UNREPLAYED" for row in ordered),
        "evaluated_not_applicable": sum(row["status"] == "EVALUATED_NOT_APPLICABLE" for row in ordered),
        "unobserved_strategies": sum(row["status"] == "NOT_OBSERVED" for row in ordered),
        "unlinked_confirmed_outcomes": unlinked_confirmed,
        "decision_analysis_aggregates": bool(isinstance(per_strategy, Mapping) and per_strategy),
        "book_inventory": [
            {
                "book": item.get("file") or item.get("book") or item.get("source_title"),
                "book_hash": item.get("file_hash") or item.get("source_hash"),
                "status": item.get("status"),
                "words": item.get("words"),
            }
            for item in (library.get("books") or [])
            if isinstance(item, Mapping)
        ],
        "strategies": ordered,
        "books": sorted(books.values(), key=lambda row: str(row["book"])),
    }


def render_strategy_report(report: Mapping[str, Any], *, limit: int | None = 25) -> str:
    rows = list(report.get("strategies") or [])
    if limit is not None:
        rows = rows[:max(0, int(limit))]
    lines = [
        "================ WATCHER STRATEGY OUTCOMES ================",
        f"CORPUS_VERSION={report.get('corpus_version')}",
        f"CORPUS_BOOKS={len(report.get('book_inventory') or [])} BOOKS_WITH_STRATEGIES={len(report.get('books') or [])}",
        f"TOTAL_STRATEGIES={report.get('total_strategies', 0)} OBSERVED={report.get('observed_strategies', 0)} APPLICABLE_UNREPLAYED={report.get('applicable_unreplayed', 0)} EVALUATED_NOT_APPLICABLE={report.get('evaluated_not_applicable', 0)} UNOBSERVED={report.get('unobserved_strategies', 0)}",
        f"UNLINKED_BROKER_OUTCOMES={report.get('unlinked_confirmed_outcomes', 0)}",
        "BOOK / STUDY OUTCOMES",
        "BOOK | STRATEGIES | APPLICABLE | SHADOW_CLOSED | BROKER_CONFIRMED | WINS | LOSSES | NET_USD",
    ]
    for book in report.get("books") or []:
        lines.append(" | ".join([
            _text(book.get("book")), str(book.get("strategies", 0)),
            str(book.get("applicable_decisions", 0)), str(book.get("shadow_closed", 0)),
            str(book.get("confirmed_outcomes", 0)), str(book.get("wins", 0)),
            str(book.get("losses", 0)), f"{float(book.get('net_pnl_usd') or 0.0):.4f}",
        ]))
    lines.extend([
        "STRATEGY OUTCOMES",
        "STATUS | EVIDENCE | SIDE | BOOK | FAMILY | EVALUATED | APPLICABLE | SHADOW_CLOSED | BROKER_CONFIRMED | BROKER_NET_WIN_RATE | EXACT_WIN_RATE | PROXY_WIN_RATE | WINS | LOSSES | NET_USD | RECORD_ID",
    ])
    for row in rows:
        net = row.get("net_pnl_usd")
        net_text = "-" if net is None else f"{float(net):.4f}"
        broker_rate = row.get("broker_net_win_rate_percent")
        broker_rate_text = "-" if broker_rate is None else f"{float(broker_rate):.2f}%"
        exact_rate = row.get("exact_win_rate_percent")
        exact_rate_text = "-" if exact_rate is None else f"{float(exact_rate):.2f}%"
        proxy_rate = row.get("proxy_win_rate_percent")
        proxy_rate_text = "-" if proxy_rate is None else f"{float(proxy_rate):.2f}%"
        lines.append(" | ".join([
            _text(row.get("status")), _text(row.get("evidence_status")), _text(row.get("side_rule")), _text(row.get("book")), _text(row.get("strategy_family")),
            str(row.get("evaluated_decisions", 0)), str(row.get("applicable_decisions", 0)), str(row.get("shadow_closed", 0)),
            str(row.get("confirmed_outcomes", 0)), broker_rate_text, exact_rate_text, proxy_rate_text, str(row.get("wins", 0)), str(row.get("losses", 0)),
            net_text, _text(row.get("record_id")),
        ]))
    lines.append("=============================================================")
    return "\n".join(lines)


def write_strategy_report(report_dir: Path) -> dict[str, Any]:
    report = build_strategy_report(report_dir)
    path = Path(report_dir) / "strategy_outcome_report.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    markdown = ["# Watcher strategy outcomes", "", render_strategy_report(report, limit=None), ""]
    (Path(report_dir) / "strategy_outcome_report.md").write_text("\n".join(markdown), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show Watcher-only outcomes for every strategy")
    parser.add_argument("--reports", type=Path, default=ROOT / "reports" / "watcher")
    parser.add_argument("--all", action="store_true", help="print every strategy instead of the top 25")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    report = write_strategy_report(args.reports)
    if args.json_only:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render_strategy_report(report, limit=None if args.all else args.top))
        print(f"REPORT_JSON={Path(args.reports) / 'strategy_outcome_report.json'}")
        print(f"REPORT_MARKDOWN={Path(args.reports) / 'strategy_outcome_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
