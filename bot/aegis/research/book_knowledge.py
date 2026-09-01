"""Deterministic book-corpus operationalization (spec sections A, L).

Processes EVERY source under docs/trading/books/ into a structured research
knowledge base under bot/knowledge/. No LLM in the loop: classification is
rule/keyword-based and fully deterministic, restart-safe (content-hash skip),
and every file gets an explicit status - nothing is silently skipped:

  INDEXED | PARTIALLY_INDEXED | FAILED | UNSUPPORTED | PLACEHOLDER | OCR_DEGRADED

Original passages remain AUTHORITATIVE: every record stores its source
location (char span + line span) and a passage hash back into the raw text.

Knowledge-type taxonomy (not every passage becomes a strategy):
  DESCRIPTIVE | STRATEGY_HYPOTHESIS | ENTRY_PRINCIPLE | EXIT_PRINCIPLE |
  RISK_PRINCIPLE | EXECUTION_PRINCIPLE | VALIDATION_PRINCIPLE

Conflicting authors are NEVER merged: continuation and failed-breakout-fade
become two separate falsifiable hypotheses with opposite polarity tags under
the same conflict topic. Book consensus does not authorise trades.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED_EXT = {".md", ".markdown", ".txt"}
PLACEHOLDER_MAX_WORDS = 30
PARTIAL_MAX_WORDS = 400
OCR_GARBLED_RATIO = 0.35

# Cache identity (audited fix 6): source hash ALONE is insufficient - when the
# extraction code changes, old records must not be reused. Bump
# EXTRACTION_VERSION on any classifier/formalizer change.
EXTRACTION_VERSION = "2"
SCHEMA_VERSION = "corpus_manifest.v2"
COMPILER_VERSION = "book_knowledge.py@extraction_" + EXTRACTION_VERSION

STATUS_INDEXED = "INDEXED"
STATUS_PARTIAL = "PARTIALLY_INDEXED"
STATUS_FAILED = "FAILED"
STATUS_UNSUPPORTED = "UNSUPPORTED"
STATUS_PLACEHOLDER = "PLACEHOLDER"
STATUS_OCR = "OCR_DEGRADED"

TYPE_DESCR = "DESCRIPTIVE"
TYPE_STRATEGY = "STRATEGY_HYPOTHESIS"
TYPE_ENTRY = "ENTRY_PRINCIPLE"
TYPE_EXIT = "EXIT_PRINCIPLE"
TYPE_RISK = "RISK_PRINCIPLE"
TYPE_EXECUTION = "EXECUTION_PRINCIPLE"
TYPE_VALIDATION = "VALIDATION_PRINCIPLE"

# Exit-knowledge categories the spec explicitly requires (section L).
EXIT_CATEGORIES = {
    "taking_profits": ("take profit", "taking profits", "profit target"),
    "letting_winners_run": ("let winners run", "letting winners run", "run their profits"),
    "trailing_stops": ("trailing stop", "trail the stop", "trailing"),
    "structural_exits": ("structure break", "below support", "above resistance",
                         "trendline break"),
    "time_stops": ("time stop", "time-based exit", "hold period"),
    "failed_breakouts": ("failed breakout", "false breakout", "failed break"),
    "momentum_decay": ("momentum decay", "losing momentum", "divergence"),
    "mfe_mae": ("maximum favorable", "favorable excursion", "adverse excursion"),
    "risk_reward": ("risk/reward", "reward to risk", "risk-reward"),
    "volatility_exits": ("volatility contract", "atr exit", "volatility drop"),
    "scaling_out": ("scale out", "scaling out", "partial profit"),
    "trend_termination": ("trend termination", "end of the trend", "trend change"),
    "mean_reversion_completion": ("mean reversion complete", "reversion target",
                                  "fair value", "returns to the mean"),
}

# Spec defect 5: SOURCE_KNOWLEDGE vs EXECUTABLE_RESEARCH_HYPOTHESIS.
# A tagged passage is knowledge; an executable hypothesis needs formalized
# logic fields. Non-executable strategy passages stay SOURCE_KNOWLEDGE only.
_FAMILY_MAP = (
    (("failed breakout", "false breakout"), "failed_breakout_fade", "fade"),
    (("breakout",), "breakout_continuation", "continuation"),
    (("pullback", "retest"), "pullback_entry", "fade"),
    (("mean reversion", "reversion"), "mean_reversion", "fade"),
    (("momentum",), "momentum_continuation", "continuation"),
    (("trend",), "trend_following", "continuation"),
    (("range",), "range_fade", "fade"),
)
_SIDE_LONG = re.compile(r"\b(buy|long|bullish)\b", re.I)
_SIDE_SHORT = re.compile(r"\b(sell|short|bearish|fade)\b", re.I)
_TF_RE = re.compile(r"\b(M1|M5|M15|M30|H1|H4|D1|daily|hourly)\b", re.I)


def _formalize(body: str, extras: dict[str, Any]) -> dict[str, Any]:
    """Derive executable-hypothesis fields from passage text deterministically.

    Returns the extra record fields; ``executable`` is True only when ALL
    required logic fields are non-empty (label alone is never enough).
    """
    lowered = body.lower()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
    family = mechanism = ""
    polarity = extras.get("polarity") or ""
    for keys, fam, pol in _FAMILY_MAP:
        if any(k in lowered for k in keys):
            family, polarity = fam, polarity or pol
            break
    if family:
        mechanism = (
            f"{polarity}: {family} edge arises from {extras.get('conflict_topic') or family} "
            "behavior described by the source; entry follows the stated trigger, "
            "invalidation at the stated structural level"
        )
    side = ""
    m_long, m_short = _SIDE_LONG.search(lowered), _SIDE_SHORT.search(lowered)
    if polarity == "fade":
        side = "sell" if m_short else ("buy" if m_long and not m_short else "")
    elif polarity == "continuation":
        side = "buy" if m_long else ("sell" if m_short and not m_long else "")
    elif m_long and not m_short:
        side = "buy"
    elif m_short and not m_long:
        side = "sell"

    def _sentence_with(pattern: re.Pattern) -> str:
        for s in sentences:
            if pattern.search(s):
                return s[:300]
        return ""

    entry_h = _sentence_with(re.compile(
        r"\b(buy|sell|enter|entry|long|short|fade)\b", re.I))
    invalid_h = _sentence_with(_INVALIDATION_CUE)
    exit_h = ""
    for cat_kws in EXIT_CATEGORIES.values():
        for kw in cat_kws:
            for s in sentences:
                if kw.lower() in s.lower():
                    exit_h = s[:300]
                    break
            if exit_h:
                break
        if exit_h:
            break
    if not exit_h:
        # Explicit executable fallback exit plan (PM policies own it).
        exit_h = "structural/time-stop per PM policies"
    tf_match = _TF_RE.search(body)
    timeframe = tf_match.group(1).upper() if tf_match else ""
    regime_topic = extras.get("conflict_topic") or ""
    falsification = extras.get(
        "falsification_condition",
        "OOS trades of this rule show expectancy <= 0 after costs",
    )

    executable = bool(
        family and mechanism and side and entry_h and invalid_h
        and exit_h and regime_topic and falsification
    )
    return {
        "strategy_family": family,
        "mechanism": mechanism,
        "side_rule": side,
        "entry_hypothesis": entry_h,
        "invalidation_hypothesis": invalid_h,
        "exit_hypothesis": exit_h or "structural/time-stop per PM policies",
        "profit_management_hypothesis": (
            "; ".join(extras.get("exit_categories", [])) or ""
        ),
        "required_regime": regime_topic,
        "required_timeframe": timeframe or "unspecified",
        "required_data": "completed_m1+m15_structure",
        "known_limitation": "",
        "falsification_condition": falsification,
        "executable": executable,
        "polarity": polarity,
    }

_KEYWORD_SETS: list[tuple[str, str, tuple[str, ...]]] = [
    ("exit", TYPE_EXIT, (
        "trailing stop", "take profit", "profit target", "exit", "let winners run",
        "time stop", "failed breakout", "momentum decay", "scale out", "give back",
        "close the position", "stop out",
    )),
    ("risk", TYPE_RISK, (
        "position sizing", "risk per trade", "stop placement", "stop-loss",
        "drawdown", "risk of ruin", "kelly", "money management", "1% rule",
    )),
    ("validation", TYPE_VALIDATION, (
        "out-of-sample", "walk-forward", "monte carlo", "overfitting", "purged",
        "embargo", "data snooping", "sample size", "backtest", "paper trading",
    )),
    ("execution", TYPE_EXECUTION, (
        "spread", "slippage", "latency", "limit order", "market order",
        "margin", "fill", "liquidity",
    )),
    ("entry", TYPE_ENTRY, (
        "entry trigger", "enter long", "enter short", "buy signal", "sell signal",
        "pullback entry", "breakout entry", "confirmation",
    )),
]

_STRATEGY_CUE = re.compile(
    r"\b(long|short|buy|sell|fade)\b.*\b(breakout|pullback|retest|trend|range|"
    r"momentum|mean reversion|reversal|continuation)\b|\b(breakout|pullback|"
    r"retest|trend|range|momentum|mean reversion|reversal|continuation)\b.*\b"
    r"(long|short|buy|sell|fade)\b", re.I | re.S,
)
_INVALIDATION_CUE = re.compile(r"\b(stop|invalidat|fail|below|above|beyond)\b", re.I)
_POLARITY_CONTINUATION = re.compile(
    r"\b(continuation|breakout .*(succeed|run)|strong trend|momentum .*(build|confirm))\b", re.I)
_POLARITY_FADE = re.compile(
    r"\b(failed breakout|false breakout|fade|exhaustion|reversal|trap)\b", re.I)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _author_from_name(stem: str) -> str:
    known = ("brooks", "davey", "chan", "de prado", "lopez de prado", "coulling",
             "johnson", "damir", "hale", "volman")
    lowered = stem.lower()
    for name in known:
        if name in lowered:
            return name.title()
    return ""


@dataclass
class SectionRecord:
    book: str
    author: str
    file_hash: str
    chapter: str
    section: str
    location: dict[str, Any]
    passage_hash: str
    passage_excerpt: str
    concept_type: str
    strategy_family: str = ""
    mechanism: str = ""
    required_regime: str = ""
    required_timeframe: str = ""
    required_data: str = ""
    entry_hypothesis: str = ""
    confirmation_hypothesis: str = ""
    invalidation_hypothesis: str = ""
    exit_hypothesis: str = ""
    profit_management_hypothesis: str = ""
    risk_principle: str = ""
    execution_principle: str = ""
    known_limitation: str = ""
    falsification_condition: str = ""
    polarity: str = ""
    conflict_topic: str = ""
    exit_categories: list[str] = field(default_factory=list)
    strategy_family: str = ""
    mechanism: str = ""
    side_rule: str = ""
    required_regime: str = ""
    required_timeframe: str = ""
    required_data: str = ""
    entry_hypothesis: str = ""
    confirmation_hypothesis: str = ""
    invalidation_hypothesis: str = ""
    exit_hypothesis: str = ""
    profit_management_hypothesis: str = ""
    falsification_condition: str = ""
    executable: bool = False
    concept_note: str = ""
    exit_categories: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _split_sections(text: str) -> list[dict[str, Any]]:
    """Split markdown into heading-scoped sections with char/line spans."""
    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    current_h1 = ""
    buf: list[str] = []
    start_line = 0
    offset = 0
    sec_start_offset = 0

    def flush(end_line: int) -> None:
        nonlocal buf, sec_start_offset
        body = "\n".join(buf).strip()
        if body:
            sections.append({
                "chapter": current_h1,
                "body": body,
                "start_line": start_line,
                "end_line": end_line,
                "start_char": sec_start_offset,
                "end_char": sec_start_offset + len("\n".join(buf)),
            })
        buf = []

    for i, line in enumerate(lines):
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            flush(i)
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if level == 1:
                current_h1 = title
            buf = [line]
            start_line = i + 1
            sec_start_offset = offset
        else:
            if not buf:
                buf = []
                start_line = i + 1
                sec_start_offset = offset
            buf.append(line)
        offset += len(line) + 1
    flush(len(lines))
    return sections


def _classify(body: str) -> tuple[str, dict[str, Any]]:
    """Rule-based classification into exactly one primary type + extras."""
    lowered = body.lower()
    extras: dict[str, Any] = {}
    scores: list[tuple[int, str]] = []
    for _, typ, kws in _KEYWORD_SETS:
        hits = sum(1 for kw in kws if kw in lowered)
        if hits:
            scores.append((hits, typ))
    scores.sort(reverse=True)

    is_strategy = bool(_STRATEGY_CUE.search(body)) and bool(_INVALIDATION_CUE.search(body))
    if is_strategy and scores and scores[0][1] in {TYPE_ENTRY, TYPE_EXIT}:
        primary = TYPE_STRATEGY
    elif scores:
        primary = scores[0][1]
    elif is_strategy:
        primary = TYPE_STRATEGY
    else:
        primary = TYPE_DESCR

    # Exit-category tags (spec section L).
    cats = []
    for cat, kws in EXIT_CATEGORIES.items():
        if any(kw in lowered for kw in kws):
            cats.append(cat)
    if cats:
        extras["exit_categories"] = cats

    # Polarity / conflict topic for strategy hypotheses.
    if primary in {TYPE_STRATEGY, TYPE_ENTRY}:
        cont = bool(_POLARITY_CONTINUATION.search(body))
        fade = bool(_POLARITY_FADE.search(body))
        if cont and not fade:
            extras["polarity"] = "continuation"
        elif fade and not cont:
            extras["polarity"] = "fade"
        elif cont and fade:
            # Both discussed: record dominant by last mention order.
            extras["polarity"] = (
                "continuation" if _POLARITY_CONTINUATION.search(body).start()
                < _POLARITY_FADE.search(body).start() else "fade"
            )
        topic_match = re.search(
            r"\b(breakout|pullback|retest|trend|range|momentum|mean reversion|reversal)\b",
            lowered,
        )
        if topic_match:
            extras["conflict_topic"] = topic_match.group(1)
        if primary == TYPE_STRATEGY:
            extras.setdefault("falsification_condition",
                              "OOS trades of this rule show expectancy <= 0 after costs")
    return primary, extras


def process_book(path: Path, *, repo_root: Path) -> dict[str, Any]:
    """Process one source file. Returns file report + extracted records."""
    rel = str(path.relative_to(repo_root))
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXT:
        return {"file": rel, "status": STATUS_UNSUPPORTED,
                "reason": f"unsupported extension {ext}", "records": []}
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"file": rel, "status": STATUS_FAILED,
                "reason": str(exc)[:160], "records": []}
    file_hash = _sha256(raw)
    words = len(re.findall(r"[A-Za-z]{2,}", raw))
    if words == 0:
        return {"file": rel, "status": STATUS_PLACEHOLDER, "words": 0,
                "file_hash": file_hash, "records": []}
    letters = len(re.findall(r"[A-Za-z]", raw))
    garbled = 1.0 - (letters / max(1, len(raw)))
    status = STATUS_INDEXED
    if words < PLACEHOLDER_MAX_WORDS:
        status = STATUS_PLACEHOLDER
    elif words < PARTIAL_MAX_WORDS:
        status = STATUS_PARTIAL
    elif garbled > OCR_GARBLED_RATIO:
        status = STATUS_OCR

    author = _author_from_name(path.stem)
    records: list[dict[str, Any]] = []
    for sec in _split_sections(raw):
        body = sec["body"]
        if len(re.findall(r"[A-Za-z]{2,}", body)) < 25:
            continue
        primary, extras = _classify(body)
        head = " ".join(body.split())[:400]
        formal: dict[str, Any] = {}
        if primary == TYPE_STRATEGY:
            formal = _formalize(body, extras)
            if not formal.get("executable"):
                # Label alone is SOURCE_KNOWLEDGE, not an executable hypothesis.
                primary = TYPE_DESCR
                formal["concept_note"] = (
                    "strategy-tagged passage lacked formalizable logic; kept as source knowledge"
                )
        rec = SectionRecord(
            book=path.stem,
            author=author,
            file_hash=file_hash,
            chapter=sec["chapter"],
            section=(sec["chapter"] or Path(rel).stem),
            location={"file": rel, "start_char": sec["start_char"],
                      "end_char": sec["end_char"],
                      "start_line": sec["start_line"], "end_line": sec["end_line"]},
            passage_hash=_sha256(body),
            passage_excerpt=head,
            concept_type=primary,
            polarity=formal.get("polarity", extras.get("polarity", "")),
            conflict_topic=extras.get("conflict_topic", ""),
            exit_categories=extras.get("exit_categories", []),
            strategy_family=formal.get("strategy_family", ""),
            mechanism=formal.get("mechanism", ""),
            side_rule=formal.get("side_rule", ""),
            required_regime=formal.get("required_regime", ""),
            required_timeframe=formal.get("required_timeframe", ""),
            required_data=formal.get("required_data", ""),
            entry_hypothesis=formal.get("entry_hypothesis", ""),
            confirmation_hypothesis="",
            invalidation_hypothesis=formal.get("invalidation_hypothesis", ""),
            exit_hypothesis=formal.get("exit_hypothesis", ""),
            profit_management_hypothesis=formal.get("profit_management_hypothesis", ""),
            falsification_condition=formal.get("falsification_condition", ""),
            executable=bool(formal.get("executable")),
            concept_note=formal.get("concept_note", ""),
        )
        records.append(rec.as_dict())
    return {"file": rel, "status": status, "words": words,
            "file_hash": file_hash, "records": records}


TYPE_TO_FILE = {
    TYPE_STRATEGY: "strategy_hypotheses.jsonl",
    TYPE_ENTRY: "entry_patterns.jsonl",
    TYPE_EXIT: "exit_patterns.jsonl",
    TYPE_RISK: "risk_rules.jsonl",
    TYPE_EXECUTION: "execution_rules.jsonl",
    TYPE_VALIDATION: "validation_rules.jsonl",
}


def build_knowledge_base(
    books_dir: Path,
    out_dir: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Rebuild the knowledge base. Restart-safe: unchanged files (same content
    hash in the existing manifest) are skipped unless force=True."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "corpus_manifest.json"
    old_manifest: dict[str, Any] = {}
    try:
        old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    old_by_file = {f.get("file"): f for f in old_manifest.get("files", [])}

    sources = sorted(p for p in books_dir.rglob("*") if p.is_file())
    files_report: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    for path in sources:
        rel = str(path.relative_to(books_dir.parent))
        prev = old_by_file.get(rel)
        # Cache identity (audited fix 6): source hash AND extraction version.
        same_extraction = (
            str(old_manifest.get("extraction_version") or "") == EXTRACTION_VERSION
        )
        if prev and not force and prev.get("file_hash") and same_extraction:
            # Restart-safe reuse ONLY when content is unchanged.
            try:
                current_hash = _sha256(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                current_hash = None
            cached = prev.get("_records") or []
            if current_hash == prev.get("file_hash") and cached:
                files_report.append({k: v for k, v in prev.items() if k != "_records"})
                all_records.extend(cached)
                continue
        report = process_book(path, repo_root=books_dir.parent)
        report["_records"] = report.pop("records")
        files_report.append(report)
        all_records.extend(report["_records"])

    # Write typed sinks.
    written: dict[str, int] = {}
    handles: dict[str, Any] = {}
    try:
        for rec in all_records:
            sink = TYPE_TO_FILE.get(rec["concept_type"])
            targets = ["concepts.jsonl"]
            if sink:
                targets.append(sink)
            for name in targets:
                if name not in handles:
                    handles[name] = (out_dir / name).open("w", encoding="utf-8")
                    written[name] = 0
                handles[name].write(json.dumps(rec, sort_keys=True) + "\n")
                written[name] += 1
    finally:
        for fh in handles.values():
            fh.close()

    corpus_version = _sha256(
        "\n".join(sorted(
            [f"{f['file']}:{f.get('file_hash')}" for f in files_report]
            + [f"extraction:{EXTRACTION_VERSION}",
               f"compiler:{COMPILER_VERSION}"]
        ))
    )
    source_index = {
        "schema": "book_source_index.v1",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "corpus_version": corpus_version,
        "files": [{k: v for k, v in f.items() if k != "_records"} for f in files_report],
        "counts_by_status": {},
    }
    for f in files_report:
        st = f["status"]
        source_index["counts_by_status"][st] = source_index["counts_by_status"].get(st, 0) + 1
    (out_dir / "source_index.json").write_text(
        json.dumps(source_index, indent=2, sort_keys=True), encoding="utf-8")

    # Persist records inside the manifest for restart-safe reuse.
    manifest_path.write_text(json.dumps(
        {"schema": SCHEMA_VERSION,
         "built_utc": datetime.now(timezone.utc).isoformat(),
         "corpus_version": corpus_version,
         "extraction_version": EXTRACTION_VERSION,
         "compiler_version": COMPILER_VERSION,
         "files": files_report},
        indent=2, sort_keys=True, default=str), encoding="utf-8")
    counts: dict[str, int] = {}
    for rec in all_records:
        counts[rec["concept_type"]] = counts.get(rec["concept_type"], 0) + 1
    return {
        "corpus_version": corpus_version,
        "files": len(files_report),
        "records": len(all_records),
        "counts_by_type": counts,
        "counts_by_status": source_index["counts_by_status"],
        "written": written,
    }
